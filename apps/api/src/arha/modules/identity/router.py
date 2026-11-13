from __future__ import annotations

import uuid


from fastapi import APIRouter, Depends, Response
from fastapi.responses import RedirectResponse

from arha.core import ratelimit
from arha.core.context import Ctx, authenticated, cookie_name, public_route
from arha.core.errors import AppError, NotFound
from arha.db.session import set_user
from arha.modules.identity import schemas as s
from arha.modules.identity import service
from arha.modules.identity.models import Session, User
from arha.modules.messaging import service as mail
from arha.modules.orgs import service as orgs
from arha.modules.trust import service as trust
from arha.settings import get_settings

router = APIRouter(prefix="/v1", tags=["identity"])


def _set_cookie(response: Response, token: str) -> None:
    st = get_settings()
    response.set_cookie(cookie_name(), token, httponly=True, secure=st.cookie_secure, samesite="lax", path="/",
                        max_age=st.session_idle_days * 86400)


async def _me(ctx: Ctx, user: User, sess: Session) -> s.MeOut:
    members = await orgs.memberships_of_user(ctx.db, user.id)
    return s.MeOut(id=user.id, email=user.email, display_name=user.display_name, locale=user.locale,
                   email_verified=user.email_verified_at is not None, totp_enabled=user.totp_enabled_at is not None,
                   mfa_passed=sess.mfa_passed, is_platform_admin=user.is_platform_admin,
                   csrf_token=sess.csrf_token, memberships=[s.MembershipOut(**m) for m in members])


async def _send_link(ctx: Ctx, user_email: str, locale: str, purpose: str, user_id: uuid.UUID | None) -> None:
    token = await service.issue_email_token(ctx.db, email=user_email, purpose=purpose, user_id=user_id)
    path = {"verify_email": "verify-email", "magic_link": "magic", "password_reset": "reset-password"}[purpose]
    link = f"{get_settings().arha_app_url}/auth/{path}?token={token}"
    subject, body = mail.render(purpose, locale, link=link)
    await mail.send(mail.Mail(to=user_email, subject=subject, text=body, template=purpose))


async def _login(ctx: Ctx, response: Response, user: User, *, mfa_passed: bool) -> s.MeOut:
    token, sess = await service.open_session(ctx.db, user, ip_hash=ctx.ip_hash,
                                             user_agent=ctx.request.headers.get("user-agent"),
                                             mfa_passed=mfa_passed)
    _set_cookie(response, token)
    await set_user(ctx.db, user.id)
    await trust.audit(ctx.db, "auth.login", org_id=None, actor_id=user.id, ip_hash=ctx.ip_hash)
    return await _me(ctx, user, sess)


@router.post("/auth/signup", response_model=s.MeOut, status_code=201)
async def signup(body: s.SignupIn, response: Response, ctx: Ctx = Depends(public_route)) -> s.MeOut:
    await ratelimit.limit("signup", ctx.ip_hash or "")
    user = await service.create_user(ctx.db, email=body.email, password=body.password, locale=body.locale,
                                     display_name=body.display_name)
    await _send_link(ctx, user.email, user.locale, "verify_email", user.id)
    return await _login(ctx, response, user, mfa_passed=False)


@router.post("/auth/login", response_model=s.MeOut)
async def login(body: s.LoginIn, response: Response, ctx: Ctx = Depends(public_route)) -> s.MeOut:
    await ratelimit.limit("login", ctx.ip_hash or "")
    user = await service.authenticate(ctx.db, body.email, body.password)
    mfa_passed = False
    if user.totp_enabled_at is not None:
        if not body.totp_code:
            raise AppError("mfa_code_required", 401)
        if not service.verify_totp(user, body.totp_code):
            raise AppError("mfa_code_invalid", 401)
        mfa_passed = True
    return await _login(ctx, response, user, mfa_passed=mfa_passed)


@router.post("/auth/verify-email", status_code=204)
async def verify_email(body: s.TokenIn, ctx: Ctx = Depends(public_route)) -> None:
    tok = await service.consume_email_token(ctx.db, body.token, "verify_email")
    if tok.user_id:
        user = await service.get_user(ctx.db, tok.user_id)
        from arha.core import clock
        user.email_verified_at = user.email_verified_at or clock.now()


@router.post("/auth/resend-verification", status_code=204)
async def resend_verification(ctx: Ctx = Depends(authenticated)) -> None:
    user = await service.get_user(ctx.db, ctx.user_id)
    if user.email_verified_at is None:
        await ratelimit.limit("signup", ctx.ip_hash or "")
        await _send_link(ctx, user.email, user.locale, "verify_email", user.id)


@router.post("/auth/magic-link", status_code=202)
async def magic_link(body: s.EmailIn, ctx: Ctx = Depends(public_route)) -> dict[str, str]:
    await ratelimit.limit("login", ctx.ip_hash or "")
    user = await service.find_by_email(ctx.db, body.email)
    if user is not None and user.disabled_at is None:
        await _send_link(ctx, user.email, user.locale, "magic_link", user.id)
    return {"status": "sent"}  # identical answer whether the account exists or not


@router.post("/auth/magic-link/consume", response_model=s.MeOut)
async def magic_consume(body: s.TokenIn, response: Response, ctx: Ctx = Depends(public_route)) -> s.MeOut:
    tok = await service.consume_email_token(ctx.db, body.token, "magic_link")
    assert tok.user_id
    user = await service.get_user(ctx.db, tok.user_id)
    from arha.core import clock
    user.email_verified_at = user.email_verified_at or clock.now()
    if user.totp_enabled_at is not None:
        # A magic link proves e-mail ownership only; MFA still applies before privileged actions.
        return await _login(ctx, response, user, mfa_passed=False)
    return await _login(ctx, response, user, mfa_passed=False)


@router.post("/auth/password-reset", status_code=202)
async def password_reset(body: s.EmailIn, ctx: Ctx = Depends(public_route)) -> dict[str, str]:
    await ratelimit.limit("login", ctx.ip_hash or "")
    user = await service.find_by_email(ctx.db, body.email)
    if user is not None:
        await _send_link(ctx, user.email, user.locale, "password_reset", user.id)
    return {"status": "sent"}


@router.post("/auth/password-reset/confirm", status_code=204)
async def password_reset_confirm(body: s.PasswordResetIn, ctx: Ctx = Depends(public_route)) -> None:
    tok = await service.consume_email_token(ctx.db, body.token, "password_reset")
    assert tok.user_id
    await service.check_password_policy(body.password)
    user = await service.get_user(ctx.db, tok.user_id)
    from arha.core.security import hash_password
    user.password_hash = hash_password(body.password)
    for sess in await service.list_sessions(ctx.db, user.id):
        await service.revoke_session(ctx.db, user.id, sess.id)
    await set_user(ctx.db, user.id)
    await trust.audit(ctx.db, "auth.password_reset", org_id=None, actor_id=user.id, ip_hash=ctx.ip_hash)


@router.get("/auth/google/start")
async def google_start(ctx: Ctx = Depends(public_route)) -> RedirectResponse:
    from arha.modules.identity import google
    return await google.start(ctx)


@router.get("/auth/google/callback")
async def google_callback(code: str, state: str, ctx: Ctx = Depends(public_route)) -> RedirectResponse:
    from arha.modules.identity import google
    user = await google.finish(ctx, code, state)
    redirect = RedirectResponse(f"{get_settings().arha_app_url}/", status_code=303)
    token, _ = await service.open_session(ctx.db, user, ip_hash=ctx.ip_hash,
                                          user_agent=ctx.request.headers.get("user-agent"), mfa_passed=False)
    _set_cookie(redirect, token)
    return redirect


@router.post("/auth/logout", status_code=204)
async def logout(response: Response, ctx: Ctx = Depends(authenticated)) -> None:
    assert ctx.user
    await service.revoke_session(ctx.db, ctx.user.user_id, ctx.user.session_id)
    response.delete_cookie(cookie_name(), path="/")


@router.post("/auth/mfa", response_model=s.MeOut)
async def mfa_elevate(body: s.CodeIn, response: Response, ctx: Ctx = Depends(authenticated)) -> s.MeOut:
    """Elevate the session after TOTP. The session token rotates on privilege elevation (S-02)."""
    assert ctx.user
    await ratelimit.limit("login", ctx.ip_hash or "")
    user = await service.get_user(ctx.db, ctx.user.user_id)
    if not service.verify_totp(user, body.code):
        raise AppError("mfa_code_invalid", 401)
    await service.revoke_session(ctx.db, user.id, ctx.user.session_id)
    return await _login(ctx, response, user, mfa_passed=True)


@router.get("/me", response_model=s.MeOut)
async def me(ctx: Ctx = Depends(authenticated)) -> s.MeOut:
    assert ctx.user
    found = await service.resolve_session_by_id(ctx.db, ctx.user.session_id)
    return await _me(ctx, found[1], found[0])


@router.patch("/me", response_model=s.MeOut)
async def update_me(body: s.ProfileIn, ctx: Ctx = Depends(authenticated)) -> s.MeOut:
    assert ctx.user
    sess, user = await service.resolve_session_by_id(ctx.db, ctx.user.session_id)
    if body.display_name is not None:
        user.display_name = body.display_name
    if body.locale is not None:
        user.locale = body.locale
    return await _me(ctx, user, sess)


@router.get("/me/sessions", response_model=list[s.SessionOut])
async def my_sessions(ctx: Ctx = Depends(authenticated)) -> list[s.SessionOut]:
    assert ctx.user
    rows = await service.list_sessions(ctx.db, ctx.user.user_id)
    return [s.SessionOut(id=r.id, user_agent=r.user_agent, created_at=r.created_at, last_seen_at=r.last_seen_at,
                         current=r.id == ctx.user.session_id) for r in rows]


@router.delete("/me/sessions/{session_id}", status_code=204)
async def revoke(session_id: uuid.UUID, ctx: Ctx = Depends(authenticated)) -> None:
    if not await service.revoke_session(ctx.db, ctx.user_id, session_id):
        raise NotFound()


@router.post("/me/totp/setup", response_model=s.TotpSetupOut)
async def totp_setup(ctx: Ctx = Depends(authenticated)) -> s.TotpSetupOut:
    user = await service.get_user(ctx.db, ctx.user_id)
    if user.totp_enabled_at is not None:
        raise AppError("mfa_already_enabled", 409)
    secret, uri = service.totp_provisioning(user)
    service.store_pending_totp(user, secret)
    return s.TotpSetupOut(secret=secret, otpauth_uri=uri)


@router.post("/me/totp/enable", response_model=s.BackupCodesOut)
async def totp_enable(body: s.CodeIn, ctx: Ctx = Depends(authenticated)) -> s.BackupCodesOut:
    user = await service.get_user(ctx.db, ctx.user_id)
    if user.totp_enabled_at is not None or not service.verify_totp(user, body.code):
        raise AppError("mfa_code_invalid", 400)
    codes = service.enable_totp(user)
    await trust.audit(ctx.db, "auth.mfa_enabled", org_id=None, actor_id=user.id, ip_hash=ctx.ip_hash)
    return s.BackupCodesOut(backup_codes=codes)


@router.post("/me/totp/disable", status_code=204)
async def totp_disable(body: s.CodeIn, ctx: Ctx = Depends(authenticated)) -> None:
    user = await service.get_user(ctx.db, ctx.user_id)
    if not service.verify_totp(user, body.code):
        raise AppError("mfa_code_invalid", 400)
    service.disable_totp(user)
    await trust.audit(ctx.db, "auth.mfa_disabled", org_id=None, actor_id=user.id, ip_hash=ctx.ip_hash)


