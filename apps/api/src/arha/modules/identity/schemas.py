from __future__ import annotations

import uuid
from datetime import datetime
from typing import Literal

from pydantic import BaseModel, ConfigDict, EmailStr, Field


class _In(BaseModel):
    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)


class SignupIn(_In):
    email: EmailStr = Field(max_length=254)
    password: str = Field(min_length=10, max_length=256)
    display_name: str | None = Field(default=None, max_length=120)
    locale: Literal["fr", "en"] = "fr"


class LoginIn(_In):
    email: EmailStr = Field(max_length=254)
    password: str = Field(min_length=1, max_length=256)
    totp_code: str | None = Field(default=None, max_length=16)


class EmailIn(_In):
    email: EmailStr = Field(max_length=254)


class TokenIn(_In):
    token: str = Field(min_length=16, max_length=128)


class PasswordResetIn(_In):
    token: str = Field(min_length=16, max_length=128)
    password: str = Field(min_length=10, max_length=256)


class CodeIn(_In):
    code: str = Field(min_length=6, max_length=16)


class ProfileIn(_In):
    display_name: str | None = Field(default=None, max_length=120)
    locale: Literal["fr", "en"] | None = None


class MembershipOut(BaseModel):
    organization_id: uuid.UUID
    name: str
    slug: str
    role: str
    plan_code: str


class MeOut(BaseModel):
    id: uuid.UUID
    email: str
    display_name: str | None
    locale: str
    email_verified: bool
    totp_enabled: bool
    mfa_passed: bool
    is_platform_admin: bool
    csrf_token: str
    memberships: list[MembershipOut]


class SessionOut(BaseModel):
    id: uuid.UUID
    user_agent: str | None
    created_at: datetime
    last_seen_at: datetime
    current: bool


class TotpSetupOut(BaseModel):
    secret: str
    otpauth_uri: str


class BackupCodesOut(BaseModel):
    backup_codes: list[str]
