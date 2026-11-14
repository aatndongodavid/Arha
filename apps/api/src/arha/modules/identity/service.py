"""Accounts, sessions, e-mail tokens and TOTP (F-AUT-01..03, S-01..S-03)."""

from __future__ import annotations

import uuid
from datetime import timedelta

import pyotp
from sqlalchemy import select, update
from sqlalchemy.ext.asyncio import AsyncSession

from arha.core import clock
from arha.core.crypto import decrypt, encrypt
from arha.core.errors import AppError, Unauthorized
from arha.core.ids import uuid7
from arha.core.security import (
    hash_password,
    is_password_pwned,
    new_token,
    sha256_hex,
    verify_password,
)
from arha.modules.identity.models import EmailToken, Session, User

TOKEN_TTL = {"verify_email": timedelta(days=3), "magic_link": timedelta(minutes=15),
             "password_reset": timedelta(hours=1)}


async def resolve_session(db: AsyncSession, token_hash: str) -> tuple[Session, User] | None:
    stmt = select(Session, User).join(User, User.id == Session.user_id).where(Session.token_hash == token_hash)
    row = (await db.execute(stmt)).first()
    return (row[0], row[1]) if row else None


async def resolve_session_by_id(db: AsyncSession, session_id: uuid.UUID) -> tuple[Session, User]:
    stmt = select(Session, User).join(User, User.id == Session.user_id).where(Session.id == session_id)
    row = (await db.execute(stmt)).first()
    if row is None:
        raise Unauthorized()
    return row[0], row[1]


async def get_user(db: AsyncSession, user_id: uuid.UUID) -> User:
    user = await db.get(User, user_id)
    if user is None:
        raise Unauthorized()
    return user


async def find_by_email(db: AsyncSession, email: str) -> User | None:
    return (await db.execute(select(User).where(User.email == email.lower()))).scalar_one_or_none()


async def check_password_policy(password: str) -> None:
    if len(password) < 10:
        raise AppError("password_too_short", 422)
    if await is_password_pwned(password):
        raise AppError("password_compromised", 422)


async def create_user(db: AsyncSession, *, email: str, password: str | None, locale: str,
                      display_name: str | None = None, google_sub: str | None = None,
                      verified: bool = False) -> User:
    if await find_by_email(db, email):
        raise AppError("email_taken", 409)
    if password is not None:
        await check_password_policy(password)
    user = User(id=uuid7(), email=email.lower(), password_hash=hash_password(password) if password else None,
                locale=locale, display_name=display_name, google_sub=google_sub,
                email_verified_at=clock.now() if verified else None)
    db.add(user)
    await db.flush()
    return user


async def authenticate(db: AsyncSession, email: str, password: str) -> User:
    user = await find_by_email(db, email)
    ok = verify_password(user.password_hash if user else None, password)
    if not ok or user is None or user.disabled_at is not None:
        raise AppError("invalid_credentials", 401)  # neutral message, no enumeration
    return user


async def open_session(db: AsyncSession, user: User, *, ip_hash: str | None, user_agent: str | None,
                       mfa_passed: bool) -> tuple[str, Session]:
    token = new_token()
    sess = Session(id=uuid7(), user_id=user.id, token_hash=sha256_hex(token), csrf_token=new_token(24),
                   ip_hash=ip_hash, user_agent=(user_agent or "")[:300], mfa_passed=mfa_passed,
                   created_at=clock.now(), last_seen_at=clock.now())
    db.add(sess)
    user.last_login_at = clock.now()
    await db.flush()
    return token, sess


async def revoke_session(db: AsyncSession, user_id: uuid.UUID, session_id: uuid.UUID) -> bool:
    res = await db.execute(update(Session).where(Session.id == session_id, Session.user_id == user_id,
                                                 Session.revoked_at.is_(None)).values(revoked_at=clock.now()))
    return bool(res.rowcount)  # type: ignore[attr-defined]


async def list_sessions(db: AsyncSession, user_id: uuid.UUID) -> list[Session]:
    stmt = select(Session).where(Session.user_id == user_id, Session.revoked_at.is_(None)).order_by(
        Session.last_seen_at.desc())
    return list((await db.execute(stmt)).scalars())


async def issue_email_token(db: AsyncSession, *, email: str, purpose: str, user_id: uuid.UUID | None) -> str:
    token = new_token()
    db.add(EmailToken(id=uuid7(), user_id=user_id, email=email.lower(), purpose=purpose,
                      token_hash=sha256_hex(token), expires_at=clock.now() + TOKEN_TTL[purpose]))
    await db.flush()
    return token


async def consume_email_token(db: AsyncSession, token: str, purpose: str) -> EmailToken:
    stmt = select(EmailToken).where(EmailToken.token_hash == sha256_hex(token), EmailToken.purpose == purpose)
    row = (await db.execute(stmt.with_for_update())).scalar_one_or_none()
    if row is None or row.used_at is not None or row.expires_at < clock.now():
        raise AppError("token_invalid", 400)
    row.used_at = clock.now()
    return row


# ------------------------------------------------------------------ TOTP (S-03)


def totp_provisioning(user: User) -> tuple[str, str]:
    secret = pyotp.random_base32()
    uri = pyotp.TOTP(secret).provisioning_uri(name=user.email, issuer_name="Arha")
    return secret, uri


def store_pending_totp(user: User, secret: str) -> None:
    user.totp_secret_enc = encrypt(secret)
    user.totp_enabled_at = None


def verify_totp(user: User, code: str) -> bool:
    if not user.totp_secret_enc:
        return False
    code = code.replace(" ", "")
    if pyotp.TOTP(decrypt(user.totp_secret_enc)).verify(code, valid_window=1):
        return True
    hashed = sha256_hex(code.upper())
    if hashed in (user.backup_codes_hash or []):
        user.backup_codes_hash = [h for h in user.backup_codes_hash if h != hashed]
        return True
    return False


def enable_totp(user: User) -> list[str]:
    codes = [new_token(6)[:10].upper() for _ in range(10)]
    user.backup_codes_hash = [sha256_hex(c) for c in codes]
    user.totp_enabled_at = clock.now()
    return codes


def disable_totp(user: User) -> None:
    user.totp_secret_enc = None
    user.totp_enabled_at = None
    user.backup_codes_hash = []


async def users_by_ids(db: AsyncSession, ids: list[uuid.UUID]) -> dict[uuid.UUID, User]:
    if not ids:
        return {}
    return {u.id: u for u in (await db.execute(select(User).where(User.id.in_(ids)))).scalars()}
