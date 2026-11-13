from __future__ import annotations

import uuid

from fastapi import APIRouter, Depends, File, Form, UploadFile

from arha.core.context import Ctx, authenticated, require_permission
from arha.core.errors import AppError, NotFound
from arha.core.features import org_features, plan_limit
from arha.core.ids import uuid7
from arha.core.storage import sniff, storage
from arha.db.session import set_org
from arha.modules.identity import service as identity
from arha.modules.messaging import service as mail
from arha.modules.orgs import schemas as s
from arha.modules.orgs import service
from arha.modules.orgs.models import Organization
from arha.modules.trust import service as trust
from arha.settings import get_settings

router = APIRouter(prefix="/v1", tags=["organizations"])
LIMIT_KEYS = ("responses_per_month", "members", "storage_gb", "max_file_mb", "version_history_days")


def _org_out(org: Organization, role: str) -> s.OrgOut:
    return s.OrgOut(id=org.id, name=org.name, slug=org.slug, plan_code=org.plan_code, country=org.country,
                    currency=org.currency, is_nonprofit=org.is_nonprofit, viewer_can_export=org.viewer_can_export,
                    verified=org.verified_at is not None, suspended=org.suspended_at is not None,
                    referral_code=org.referral_code, role=role, features=sorted(org_features(org)),
                    limits={k: plan_limit(org, k) for k in LIMIT_KEYS}, created_at=org.created_at)


@router.post("/orgs", response_model=s.OrgOut, status_code=201)
async def create_org(body: s.OrgCreateIn, ctx: Ctx = Depends(authenticated)) -> s.OrgOut:
    org = await service.create_org(ctx.db, user_id=ctx.user_id, name=body.name, country=body.country,
                                   is_nonprofit=body.is_nonprofit, referral_code=body.referral_code)
    return _org_out(org, "owner")


@router.get("/orgs/{org_id}", response_model=s.OrgOut)
async def get_org(ctx: Ctx = Depends(require_permission("org:read"))) -> s.OrgOut:
    return _org_out(ctx.org, ctx.role or "viewer")


@router.patch("/orgs/{org_id}", response_model=s.OrgOut)
async def update_org(body: s.OrgUpdateIn, ctx: Ctx = Depends(require_permission("org:settings"))) -> s.OrgOut:
    if body.name is not None:
        ctx.org.name = body.name
    if body.viewer_can_export is not None:
        ctx.org.viewer_can_export = body.viewer_can_export
    await trust.audit(ctx.db, "org.updated", org_id=ctx.org_id, actor_id=ctx.user_id,
                      metadata=body.model_dump(exclude_none=True))
    return _org_out(ctx.org, ctx.role or "viewer")


@router.get("/orgs/{org_id}/members", response_model=list[s.MemberOut])
async def members(ctx: Ctx = Depends(require_permission("org:read"))) -> list[s.MemberOut]:
    return [s.MemberOut(user_id=m.user_id, email=u.email if u else "", display_name=u.display_name if u else None,
                        role=m.role, created_at=m.created_at) for m, u in await service.list_members(ctx.db)]


@router.post("/orgs/{org_id}/invitations", response_model=s.InvitationOut, status_code=201)
async def invite(body: s.InviteIn, ctx: Ctx = Depends(require_permission("members:manage"))) -> s.InvitationOut:
    token = await service.invite(ctx.db, ctx.org, email=body.email, role=body.role, invited_by=ctx.user_id)
    link = f"{get_settings().arha_app_url}/invitations/accept?token={token}"
    subject, text_body = mail.render("invitation", ctx.locale, org=ctx.org.name, link=link)
    await mail.send(mail.Mail(to=body.email, subject=subject, text=text_body, template="invitation"),
                    db=ctx.db, org_id=ctx.org_id)
    inv = (await service.list_invitations(ctx.db))[0]
    return s.InvitationOut(id=inv.id, email=inv.email, role=inv.role, expires_at=inv.expires_at, accepted=False)


@router.get("/orgs/{org_id}/invitations", response_model=list[s.InvitationOut])
async def invitations(ctx: Ctx = Depends(require_permission("members:manage"))) -> list[s.InvitationOut]:
    return [s.InvitationOut(id=i.id, email=i.email, role=i.role, expires_at=i.expires_at,
                            accepted=i.accepted_at is not None) for i in await service.list_invitations(ctx.db)]


@router.delete("/orgs/{org_id}/invitations/{invitation_id}", status_code=204)
async def cancel_invitation(invitation_id: uuid.UUID,
                            ctx: Ctx = Depends(require_permission("members:manage"))) -> None:
    await service.cancel_invitation(ctx.db, invitation_id)


@router.post("/invitations/accept")
async def accept(body: s.AcceptIn, ctx: Ctx = Depends(authenticated)) -> dict[str, uuid.UUID]:
    assert ctx.user
    org_id = await service.accept_invitation(ctx.db, token=body.token, user_id=ctx.user.user_id,
                                             email=ctx.user.email)
    return {"organization_id": org_id}


@router.patch("/orgs/{org_id}/members/{user_id}", response_model=s.MemberOut)
async def change_role(user_id: uuid.UUID, body: s.RoleIn,
                      ctx: Ctx = Depends(require_permission("members:manage"))) -> s.MemberOut:
    assert ctx.org_id and ctx.role
    m = await service.change_role(ctx.db, actor_role=ctx.role, actor_id=ctx.user_id, org_id=ctx.org_id,
                                  user_id=user_id, role=body.role)
    u = (await identity.users_by_ids(ctx.db, [user_id])).get(user_id)
    return s.MemberOut(user_id=m.user_id, email=u.email if u else "", display_name=u.display_name if u else None,
                       role=m.role, created_at=m.created_at)


@router.delete("/orgs/{org_id}/members/{user_id}", status_code=204)
async def remove_member(user_id: uuid.UUID, ctx: Ctx = Depends(require_permission("members:manage"))) -> None:
    assert ctx.org_id and ctx.role
    await service.remove_member(ctx.db, actor_role=ctx.role, actor_id=ctx.user_id, org_id=ctx.org_id,
                                user_id=user_id)


@router.put("/orgs/{org_id}/me/notifications", status_code=204)
async def notifications(body: s.NotifyIn, ctx: Ctx = Depends(require_permission("org:read"))) -> None:
    assert ctx.org_id
    m = await service.membership_for(ctx.db, ctx.org_id, ctx.user_id)
    assert m
    m.notify_each_response = body.notify_each_response
    m.notify_daily_digest = body.notify_daily_digest


@router.get("/orgs/{org_id}/folders", response_model=list[s.FolderOut])
async def folders(ctx: Ctx = Depends(require_permission("forms:read"))) -> list[s.FolderOut]:
    return [s.FolderOut(id=f.id, name=f.name, parent_id=f.parent_id) for f in await service.list_folders(ctx.db)]


@router.post("/orgs/{org_id}/folders", response_model=s.FolderOut, status_code=201)
async def create_folder(body: s.FolderIn, ctx: Ctx = Depends(require_permission("folders:edit"))) -> s.FolderOut:
    f = await service.create_folder(ctx.db, body.name, body.parent_id)
    return s.FolderOut(id=f.id, name=f.name, parent_id=f.parent_id)


@router.patch("/orgs/{org_id}/folders/{folder_id}", response_model=s.FolderOut)
async def rename_folder(folder_id: uuid.UUID, body: s.FolderIn,
                        ctx: Ctx = Depends(require_permission("folders:edit"))) -> s.FolderOut:
    f = await service.get_folder(ctx.db, folder_id)
    f.name = body.name
    if body.parent_id != f.id:
        f.parent_id = body.parent_id
    return s.FolderOut(id=f.id, name=f.name, parent_id=f.parent_id)


@router.delete("/orgs/{org_id}/folders/{folder_id}", status_code=204)
async def delete_folder(folder_id: uuid.UUID, ctx: Ctx = Depends(require_permission("folders:edit"))) -> None:
    await ctx.db.delete(await service.get_folder(ctx.db, folder_id))


@router.post("/orgs/{org_id}/verification", status_code=202)
async def request_verification(document_type: str = Form(...), file: UploadFile = File(...),
                               ctx: Ctx = Depends(require_permission("trust:manage"))) -> dict[str, str]:
    """F-ORG-03: the organisation uploads its RCCM, association receipt or official letter."""
    if document_type not in ("rccm", "association_receipt", "official_letter"):
        raise AppError("validation_failed", 422)
    data = await file.read(10 * 1024 * 1024 + 1)
    if len(data) > 10 * 1024 * 1024:
        raise AppError("file_too_large", 413)
    if sniff(data) not in ("application/pdf", "image/png", "image/jpeg"):
        raise AppError("file_type_not_allowed", 415)
    key = f"{ctx.org_id}/verification/{uuid7()}"
    storage().put(key, data)
    await trust.request_verification(ctx.db, key, document_type)
    await trust.audit(ctx.db, "org.verification_requested", org_id=ctx.org_id, actor_id=ctx.user_id)
    return {"status": "pending"}


@router.get("/orgs/{org_id}/verification")
async def verification_status(ctx: Ctx = Depends(require_permission("org:read"))) -> dict[str, str | None]:
    req = await trust.latest_verification(ctx.db)
    return {"status": req.status if req else None, "note": req.note if req else None}


__all__ = ["NotFound", "router", "set_org"]
