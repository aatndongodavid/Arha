from __future__ import annotations

import uuid

from sqlalchemy import ARRAY, Text
from sqlalchemy.orm import Mapped, mapped_column

from arha.db.base import Base
from arha.db.types import TS, UUIDPK, Json, OrgId, TSNow, UUIDCol


class WebhookEndpoint(Base):
    __tablename__ = "webhook_endpoints"
    id: Mapped[UUIDPK]
    organization_id: Mapped[OrgId]
    form_id: Mapped[uuid.UUID | None]
    url: Mapped[str]
    secret_enc: Mapped[str]
    events: Mapped[list[str]] = mapped_column(ARRAY(Text), default=lambda: ["submission.completed"])
    active: Mapped[bool] = mapped_column(default=True)
    created_at: Mapped[TSNow]


class WebhookDelivery(Base):
    __tablename__ = "webhook_deliveries"
    id: Mapped[UUIDPK]
    organization_id: Mapped[OrgId]
    endpoint_id: Mapped[UUIDCol]
    event: Mapped[str]
    event_id: Mapped[UUIDCol]
    payload: Mapped[Json]
    payload_hash: Mapped[str]
    attempt: Mapped[int] = mapped_column(default=0)
    status_code: Mapped[int | None]
    error: Mapped[str | None]
    next_retry_at: Mapped[TS | None]
    delivered_at: Mapped[TS | None]
    failed_at: Mapped[TS | None]
    created_at: Mapped[TSNow]


class GoogleSheetsIntegration(Base):
    __tablename__ = "integrations_google_sheets"
    id: Mapped[UUIDPK]
    organization_id: Mapped[OrgId]
    form_id: Mapped[UUIDCol]
    spreadsheet_id: Mapped[str | None]
    token_enc: Mapped[str | None]
    status: Mapped[str] = mapped_column(default="pending")
    created_at: Mapped[TSNow]


class ApiKey(Base):
    __tablename__ = "api_keys"
    id: Mapped[UUIDPK]
    organization_id: Mapped[OrgId]
    name: Mapped[str]
    key_hash: Mapped[str]
    prefix: Mapped[str]
    scopes: Mapped[list[str]] = mapped_column(ARRAY(Text), default=list)
    last_used_at: Mapped[TS | None]
    revoked_at: Mapped[TS | None]
    created_at: Mapped[TSNow]
