from __future__ import annotations

import uuid
from datetime import datetime
from typing import Literal

from pydantic import BaseModel, ConfigDict, EmailStr, Field


class _In(BaseModel):
    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)


class OrgCreateIn(_In):
    name: str = Field(min_length=2, max_length=120)
    country: Literal["CM"] = "CM"
    is_nonprofit: bool = False
    referral_code: str | None = Field(default=None, max_length=32)


class OrgUpdateIn(_In):
    name: str | None = Field(default=None, min_length=2, max_length=120)
    viewer_can_export: bool | None = None


class OrgOut(BaseModel):
    id: uuid.UUID
    name: str
    slug: str
    plan_code: str
    country: str
    currency: str
    is_nonprofit: bool
    viewer_can_export: bool
    verified: bool
    suspended: bool
    referral_code: str
    role: str
    features: list[str]
    limits: dict[str, int | None]
    responses_period: str
    exports: list[str]
    payment_fee_bps: int
    created_at: datetime


class MemberOut(BaseModel):
    user_id: uuid.UUID
    email: str
    display_name: str | None
    role: str
    created_at: datetime


class InviteIn(_In):
    email: EmailStr = Field(max_length=254)
    role: Literal["admin", "editor", "viewer"]


class InvitationOut(BaseModel):
    id: uuid.UUID
    email: str
    role: str
    expires_at: datetime
    accepted: bool


class RoleIn(_In):
    role: Literal["owner", "admin", "editor", "viewer"]


class NotifyIn(_In):
    notify_each_response: bool
    notify_daily_digest: bool


class AcceptIn(_In):
    token: str = Field(min_length=16, max_length=128)


class FolderIn(_In):
    name: str = Field(min_length=1, max_length=80)
    parent_id: uuid.UUID | None = None


class FolderOut(BaseModel):
    id: uuid.UUID
    name: str
    parent_id: uuid.UUID | None
