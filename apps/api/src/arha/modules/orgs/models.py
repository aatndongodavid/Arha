from __future__ import annotations

import uuid

from sqlalchemy.orm import Mapped, mapped_column

from arha.db.base import Base
from arha.db.types import TS, UUIDPK, OrgId, TSNow, UUIDCol


class Organization(Base):
    __tablename__ = "organizations"
    id: Mapped[UUIDPK]
    name: Mapped[str]
    slug: Mapped[str]
    plan_code: Mapped[str] = mapped_column(default="discovery")
    country: Mapped[str] = mapped_column(default="CM")
    currency: Mapped[str] = mapped_column(default="XAF")
    data_region: Mapped[str] = mapped_column(default="eu-1")
    is_nonprofit: Mapped[bool] = mapped_column(default=False)
    viewer_can_export: Mapped[bool] = mapped_column(default=False)
    data_key_wrapped: Mapped[str]
    referral_code: Mapped[str]
    referred_by: Mapped[uuid.UUID | None]
    verified_at: Mapped[TS | None]
    suspended_at: Mapped[TS | None]
    suspended_reason: Mapped[str | None]
    quota_exceeded_at: Mapped[TS | None]
    created_at: Mapped[TSNow]


class Membership(Base):
    __tablename__ = "memberships"
    organization_id: Mapped[uuid.UUID] = mapped_column(primary_key=True)
    user_id: Mapped[uuid.UUID] = mapped_column(primary_key=True)
    role: Mapped[str]
    notify_each_response: Mapped[bool] = mapped_column(default=True)
    notify_daily_digest: Mapped[bool] = mapped_column(default=False)
    invited_by: Mapped[uuid.UUID | None]
    created_at: Mapped[TSNow]


class Invitation(Base):
    __tablename__ = "invitations"
    id: Mapped[UUIDPK]
    organization_id: Mapped[OrgId]
    email: Mapped[str]
    role: Mapped[str]
    token_hash: Mapped[str]
    invited_by: Mapped[UUIDCol]
    expires_at: Mapped[TS]
    accepted_at: Mapped[TS | None]
    created_at: Mapped[TSNow]


class Folder(Base):
    __tablename__ = "folders"
    id: Mapped[UUIDPK]
    organization_id: Mapped[OrgId]
    name: Mapped[str]
    parent_id: Mapped[uuid.UUID | None]
    created_at: Mapped[TSNow]
