"""Organisations, memberships, invitations and folders (F-ORG-01..04)."""

from __future__ import annotations

import re
import uuid
from datetime import timedelta
from typing import Any

from sqlalchemy import func, select, text
from sqlalchemy.ext.asyncio import AsyncSession

from arha.core import clock
from arha.core.crypto import new_data_key, wrap_key
from arha.core.errors import AppError, Conflict, NotFound
from arha.core.features import has_feature, plan_limit
from arha.core.ids import uuid7
from arha.core.security import new_token, sha256_hex, short_code
from arha.db.session import set_org
from arha.modules.orgs.models import Folder, Invitation, Membership, Organization
from arha.modules.trust import service as trust

INVITE_TTL = timedelta(days=7)


def slugify(name: str) -> str:
    import unicodedata
    base = "".join(c for c in unicodedata.normalize("NFKD", name) if not unicodedata.combining(c)).lower()
    base = re.sub(r"[^a-z0-9]+", "-", base).strip("-")[:40] or "org"
    return base if len(base) >= 2 else f"{base}-org"


async def memberships_of_user(db: AsyncSession, user_id: uuid.UUID) -> list[dict[str, Any]]:
    stmt = (select(Membership.role, Organization).join(Organization, Organization.id == Membership.organization_id)
            .where(Membership.user_id == user_id).order_by(Organization.name))
    return [{"organization_id": o.id, "name": o.name, "slug": o.slug, "role": role, "plan_code": o.plan_code}
            for role, o in (await db.execute(stmt)).all()]


async def membership_for(db: AsyncSession, org_id: uuid.UUID, user_id: uuid.UUID) -> Membership | None:
    return await db.get(Membership, (org_id, user_id))


async def get_org(db: AsyncSession, org_id: uuid.UUID) -> Organization:
    org = await db.get(Organization, org_id)
    if org is None:
        raise NotFound("organization_not_found")
    return org


async def mfa_required(db: AsyncSession, org: Organization, role: str) -> bool:
    return role == "owner" and has_feature(org, "mfa_required_owner")


async def create_org(db: AsyncSession, *, user_id: uuid.UUID, name: str, country: str, is_nonprofit: bool,
                     referral_code: str | None) -> Organization:
    org_id = uuid7()
    await set_org(db, org_id)
    # Referral attribution (ambassador programme) is resolved later by a platform job: the referrer's
    # organisation is not readable from this tenant transaction.
    referred_by = None
    base = slugify(name)
    slug = base
    for _ in range(5):
        exists = (await db.execute(text("select 1 from organizations where slug = :s"), {"s": slug})).first()
        if not exists:
            break
        slug = f"{base}-{short_code(4).lower()}"
    org = Organization(id=org_id, name=name, slug=slug, country=country, currency="XAF",
                       is_nonprofit=is_nonprofit, data_key_wrapped=wrap_key(new_data_key()),
                       referral_code=short_code(8), referred_by=referred_by)
    db.add(org)
    await db.flush()
    db.add(Membership(organization_id=org_id, user_id=user_id, role="owner"))
    await db.flush()
    await trust.audit(db, "org.created", org_id=org_id, actor_id=user_id, target_type="organization",
                      target_id=org_id, metadata={"referral_code_used": bool(referral_code)})
    return org


async def list_members(db: AsyncSession) -> list[tuple[Membership, Any]]:
    from arha.modules.identity.service import users_by_ids  # service to service

    members = list((await db.execute(select(Membership).order_by(Membership.created_at))).scalars())
    users = await users_by_ids(db, [m.user_id for m in members])
    return [(m, users.get(m.user_id)) for m in members]


async def count_members(db: AsyncSession) -> int:
    members = (await db.execute(select(func.count()).select_from(Membership))).scalar_one()
    pending = (await db.execute(select(func.count()).select_from(Invitation).where(
        Invitation.accepted_at.is_(None), Invitation.expires_at > clock.now()))).scalar_one()
    return int(members) + int(pending)


async def invite(db: AsyncSession, org: Organization, *, email: str, role: str, invited_by: uuid.UUID) -> str:
    limit = plan_limit(org, "members")
    if limit is not None and await count_members(db) >= limit:
        raise AppError("member_limit_reached", 402, params={"limit": limit})
    token = new_token()
    db.add(Invitation(id=uuid7(), organization_id=org.id, email=email.lower(), role=role,
                      token_hash=sha256_hex(token), invited_by=invited_by, expires_at=clock.now() + INVITE_TTL))
    await db.flush()
    await trust.audit(db, "member.invited", org_id=org.id, actor_id=invited_by, target_type="invitation",
                      metadata={"role": role})
    return token


async def list_invitations(db: AsyncSession) -> list[Invitation]:
    return list((await db.execute(select(Invitation).where(Invitation.accepted_at.is_(None))
                                  .order_by(Invitation.created_at.desc()))).scalars())


async def cancel_invitation(db: AsyncSession, invitation_id: uuid.UUID) -> None:
    inv = await db.get(Invitation, invitation_id)
    if inv is None or inv.accepted_at is not None:
        raise NotFound()
    await db.delete(inv)


async def accept_invitation(db: AsyncSession, *, token: str, user_id: uuid.UUID, email: str) -> uuid.UUID:
    token_hash = sha256_hex(token)
    org_id = (await db.execute(text("select resolve_org('invitation', :k)"), {"k": token_hash})).scalar()
    if org_id is None:
        raise AppError("token_invalid", 400)
    await set_org(db, org_id)
    inv = (await db.execute(select(Invitation).where(Invitation.token_hash == token_hash).with_for_update())
           ).scalar_one_or_none()
    if inv is None or inv.accepted_at is not None or inv.expires_at < clock.now():
        raise AppError("token_invalid", 400)
    if inv.email.lower() != email.lower():
        raise AppError("invitation_email_mismatch", 403)
    if await membership_for(db, org_id, user_id) is None:
        db.add(Membership(organization_id=org_id, user_id=user_id, role=inv.role, invited_by=inv.invited_by))
    inv.accepted_at = clock.now()
    await db.flush()
    await trust.audit(db, "member.joined", org_id=org_id, actor_id=user_id, metadata={"role": inv.role})
    return org_id


async def _owner_count(db: AsyncSession) -> int:
    return int((await db.execute(select(func.count()).select_from(Membership)
                                 .where(Membership.role == "owner"))).scalar_one())


async def change_role(db: AsyncSession, *, actor_role: str, actor_id: uuid.UUID, org_id: uuid.UUID,
                      user_id: uuid.UUID, role: str) -> Membership:
    member = await membership_for(db, org_id, user_id)
    if member is None:
        raise NotFound()
    if (role == "owner" or member.role == "owner") and actor_role != "owner":
        raise AppError("permission_denied", 403)
    if member.role == "owner" and role != "owner" and await _owner_count(db) <= 1:
        raise Conflict("last_owner")
    previous = member.role
    member.role = role
    await trust.audit(db, "member.role_changed", org_id=org_id, actor_id=actor_id, target_type="user",
                      target_id=user_id, metadata={"from": previous, "to": role})
    return member


async def remove_member(db: AsyncSession, *, actor_role: str, actor_id: uuid.UUID, org_id: uuid.UUID,
                        user_id: uuid.UUID) -> None:
    member = await membership_for(db, org_id, user_id)
    if member is None:
        raise NotFound()
    if member.role == "owner":
        if actor_role != "owner":
            raise AppError("permission_denied", 403)
        if await _owner_count(db) <= 1:
            raise Conflict("last_owner")
    await db.delete(member)
    await trust.audit(db, "member.removed", org_id=org_id, actor_id=actor_id, target_type="user",
                      target_id=user_id)


async def list_folders(db: AsyncSession) -> list[Folder]:
    return list((await db.execute(select(Folder).order_by(Folder.name))).scalars())


async def create_folder(db: AsyncSession, name: str, parent_id: uuid.UUID | None) -> Folder:
    if parent_id and await db.get(Folder, parent_id) is None:
        raise NotFound("folder_not_found")
    folder = Folder(id=uuid7(), name=name, parent_id=parent_id)
    db.add(folder)
    await db.flush()
    return folder


async def get_folder(db: AsyncSession, folder_id: uuid.UUID) -> Folder:
    folder = await db.get(Folder, folder_id)
    if folder is None:
        raise NotFound("folder_not_found")
    return folder


async def owners_emails(db: AsyncSession, *, only_notify: bool = False) -> list[tuple[str, str]]:
    from arha.modules.identity.service import users_by_ids

    stmt = select(Membership)
    if only_notify:
        stmt = stmt.where(Membership.notify_each_response.is_(True))
    members = list((await db.execute(stmt)).scalars())
    users = await users_by_ids(db, [m.user_id for m in members])
    return [(u.email, u.locale) for m in members if (u := users.get(m.user_id)) is not None]
