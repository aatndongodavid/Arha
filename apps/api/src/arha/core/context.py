"""Request context: authentication, CSRF, organisation scope and permission checks.

Every route must depend on exactly one of: `public_route`, `authenticated`, `require_permission(...)`,
or `platform_admin`. tests/test_route_permissions.py walks all routes and fails otherwise (S-04).
"""

from __future__ import annotations

import uuid
from collections.abc import AsyncIterator, Callable, Coroutine
from dataclasses import dataclass, field
from datetime import timedelta
from typing import Any

from fastapi import Depends, Request
from sqlalchemy import select, update
from sqlalchemy.ext.asyncio import AsyncSession

from arha.core import clock
from arha.core.errors import Forbidden, NotFound, Unauthorized
from arha.core.messages import pick_locale
from arha.core.permissions import has_permission
from arha.core.security import constant_eq, keyed_hash, sha256_hex
from arha.db.session import _app_factory, set_org, set_user
from arha.settings import get_settings

SAFE_METHODS = {"GET", "HEAD", "OPTIONS"}


def cookie_name() -> str:
    return "__Host-arha_session" if get_settings().cookie_secure else "arha_session"


@dataclass
class Principal:
    user_id: uuid.UUID
    session_id: uuid.UUID
    email: str
    locale: str
    is_platform_admin: bool
    mfa_passed: bool
    totp_enabled: bool


@dataclass
class Ctx:
    db: AsyncSession
    request: Request
    locale: str
    ip_hash: str | None
    user: Principal | None = None
    org_id: uuid.UUID | None = None
    role: str | None = None
    org: Any = None
    extras: dict[str, Any] = field(default_factory=dict)

    async def checkpoint(self) -> None:
        """Commit now and keep working in a new transaction with the same tenant context.

        Used around external calls (payment providers) so the provider is never called inside an open
        transaction, without holding a second pooled connection."""
        from arha.core import jobs

        await self.db.commit()
        await jobs.flush(self.db)
        await set_org(self.db, self.org_id)
        await set_user(self.db, self.user.user_id if self.user else None)

    @property
    def user_id(self) -> uuid.UUID:
        if self.user is None:
            raise Unauthorized()
        return self.user.user_id


def client_ip(request: Request) -> str:
    # Caddy sets X-Forwarded-For; only the first hop is trusted because Caddy overwrites it.
    fwd = request.headers.get("x-forwarded-for")
    if fwd:
        return fwd.split(",")[0].strip()
    return request.client.host if request.client else "unknown"


async def db_session() -> AsyncIterator[AsyncSession]:
    """One session per request. Committed BEFORE the response is sent (scope="function" below), so a client
    never sees a success for data that failed to commit. Jobs are deferred only after the commit."""
    from arha.core import jobs

    session = _app_factory()()
    try:
        await set_org(session, None)
        await set_user(session, None)
        yield session
        await session.commit()
        await jobs.flush(session)
    except BaseException:
        await session.rollback()
        raise
    finally:
        await session.close()


async def _base_ctx(request: Request, db: AsyncSession = Depends(db_session, scope="function")) -> Ctx:
    return Ctx(db=db, request=request, locale=pick_locale(request.headers.get("accept-language")),
               ip_hash=keyed_hash(client_ip(request)))


async def _load_principal(ctx: Ctx) -> Principal | None:
    from arha.modules.identity import service as identity  # late import, avoids cycles

    token = ctx.request.cookies.get(cookie_name())
    if not token:
        return None
    found = await identity.resolve_session(ctx.db, sha256_hex(token))
    if found is None:
        return None
    sess, user = found
    idle = timedelta(days=get_settings().session_idle_days)
    now = clock.now()
    if sess.revoked_at is not None or user.disabled_at is not None or sess.last_seen_at + idle < now:
        return None
    if now - sess.last_seen_at > timedelta(minutes=5):
        await ctx.db.execute(update(type(sess)).where(type(sess).id == sess.id).values(last_seen_at=now))
    if ctx.request.method not in SAFE_METHODS:
        header = ctx.request.headers.get("x-csrf-token", "")
        if not header or not constant_eq(header, sess.csrf_token):
            raise Forbidden("csrf_failed")
    await set_user(ctx.db, user.id)
    return Principal(user_id=user.id, session_id=sess.id, email=user.email, locale=user.locale,
                     is_platform_admin=user.is_platform_admin, mfa_passed=sess.mfa_passed,
                     totp_enabled=user.totp_enabled_at is not None)


async def public_route(ctx: Ctx = Depends(_base_ctx)) -> Ctx:
    """Explicitly public route (whitelisted). Loads the user if a session exists, never requires one."""
    try:
        ctx.user = await _load_principal(ctx)
    except Forbidden:
        ctx.user = None
    return ctx


async def authenticated(ctx: Ctx = Depends(_base_ctx)) -> Ctx:
    ctx.user = await _load_principal(ctx)
    if ctx.user is None:
        raise Unauthorized()
    return ctx


async def platform_admin(ctx: Ctx = Depends(authenticated)) -> Ctx:
    assert ctx.user is not None
    if not ctx.user.is_platform_admin:
        raise NotFound()
    if not (ctx.user.totp_enabled and ctx.user.mfa_passed):
        raise Forbidden("mfa_required")  # S-03: MFA mandatory for the internal console
    return ctx


def require_permission(permission: str) -> Callable[..., Coroutine[Any, Any, Ctx]]:
    async def dependency(org_id: uuid.UUID, ctx: Ctx = Depends(authenticated)) -> Ctx:
        from arha.modules.orgs import service as orgs

        assert ctx.user is not None
        await set_org(ctx.db, org_id)
        membership = await orgs.membership_for(ctx.db, org_id, ctx.user.user_id)
        if membership is None:
            raise NotFound("organization_not_found")  # never reveal existence (S-05)
        org = await orgs.get_org(ctx.db, org_id)
        if not has_permission(membership.role, permission, viewer_can_export=org.viewer_can_export):
            raise Forbidden("permission_denied")
        if await orgs.mfa_required(ctx.db, org, membership.role) and not (
                ctx.user.totp_enabled and ctx.user.mfa_passed):
            raise Forbidden("mfa_required")
        ctx.org_id, ctx.role, ctx.org = org_id, membership.role, org
        return ctx

    dependency.__arha_permission__ = permission  # type: ignore[attr-defined]
    return dependency


public_route.__arha_public__ = True  # type: ignore[attr-defined]
authenticated.__arha_authenticated__ = True  # type: ignore[attr-defined]
platform_admin.__arha_platform__ = True  # type: ignore[attr-defined]


async def select_one(db: AsyncSession, stmt: Any) -> Any:
    return (await db.execute(stmt)).scalar_one_or_none()


__all__ = ["Ctx", "authenticated", "platform_admin", "public_route", "require_permission", "select",
           "select_one"]
