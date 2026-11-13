from __future__ import annotations

import uuid


from sqlalchemy import ARRAY, Text
from sqlalchemy.orm import Mapped, mapped_column

from arha.db.base import Base
from arha.db.types import TS, UUIDPK, TSNow, UUIDCol


class User(Base):
    __tablename__ = "users"
    id: Mapped[UUIDPK]
    email: Mapped[str]
    email_verified_at: Mapped[TS | None]
    password_hash: Mapped[str | None]
    google_sub: Mapped[str | None]
    totp_secret_enc: Mapped[str | None]
    totp_enabled_at: Mapped[TS | None]
    backup_codes_hash: Mapped[list[str]] = mapped_column(ARRAY(Text), default=list)
    locale: Mapped[str] = mapped_column(default="fr")
    display_name: Mapped[str | None]
    is_platform_admin: Mapped[bool] = mapped_column(default=False)
    created_at: Mapped[TSNow]
    last_login_at: Mapped[TS | None]
    disabled_at: Mapped[TS | None]


class Session(Base):
    __tablename__ = "sessions"
    id: Mapped[UUIDPK]
    user_id: Mapped[UUIDCol]
    token_hash: Mapped[str]
    csrf_token: Mapped[str]
    ip_hash: Mapped[str | None]
    user_agent: Mapped[str | None]
    mfa_passed: Mapped[bool] = mapped_column(default=False)
    created_at: Mapped[TSNow]
    last_seen_at: Mapped[TSNow]
    revoked_at: Mapped[TS | None]


class EmailToken(Base):
    __tablename__ = "email_tokens"
    id: Mapped[UUIDPK]
    user_id: Mapped[uuid.UUID | None] = mapped_column()
    email: Mapped[str]
    purpose: Mapped[str]
    token_hash: Mapped[str]
    expires_at: Mapped[TS]
    used_at: Mapped[TS | None]
    created_at: Mapped[TSNow]
