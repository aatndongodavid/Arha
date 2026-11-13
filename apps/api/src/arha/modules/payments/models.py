from __future__ import annotations

import uuid
from typing import Any

from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column

from arha.db.base import Base
from arha.db.types import TS, UUIDPK, Json, Money, OrgId, TSNow, UUIDCol


class PaymentAccount(Base):
    __tablename__ = "payment_accounts"
    id: Mapped[UUIDPK]
    organization_id: Mapped[OrgId]
    provider: Mapped[str]
    provider_account_id: Mapped[str | None]
    status: Mapped[str] = mapped_column(default="pending")
    onboarding_url: Mapped[str | None]
    created_at: Mapped[TSNow]
    updated_at: Mapped[TSNow]


class Payment(Base):
    __tablename__ = "payments"
    id: Mapped[UUIDPK]
    organization_id: Mapped[OrgId]
    submission_id: Mapped[uuid.UUID | None]
    purpose: Mapped[str] = mapped_column(default="submission")
    provider: Mapped[str]
    provider_ref: Mapped[str | None]
    channel: Mapped[str | None]
    amount: Mapped[Money]
    currency: Mapped[str]
    platform_fee: Mapped[Money] = mapped_column(default=0)
    provider_fee: Mapped[Money] = mapped_column(default=0)
    fee_bearer: Mapped[str] = mapped_column(default="org")
    status: Mapped[str] = mapped_column(default="created")
    failure_reason: Mapped[str | None]
    idempotency_key: Mapped[str]
    payer_msisdn_hash: Mapped[str | None]
    receipt_number: Mapped[str | None]
    raw_events: Mapped[list[Any]] = mapped_column(JSONB, default=list)
    expires_at: Mapped[TS]
    next_poll_at: Mapped[TS | None]
    poll_attempts: Mapped[int] = mapped_column(default=0)
    created_at: Mapped[TSNow]
    updated_at: Mapped[TSNow]


class TicketCategory(Base):
    __tablename__ = "ticket_categories"
    id: Mapped[UUIDPK]
    organization_id: Mapped[OrgId]
    form_id: Mapped[UUIDCol]
    block_id: Mapped[str]
    option_id: Mapped[str]
    name: Mapped[str]
    quota: Mapped[int | None]
    price: Mapped[Money]
    issued: Mapped[int] = mapped_column(default=0)
    reserved: Mapped[int] = mapped_column(default=0)


class Ticket(Base):
    __tablename__ = "tickets"
    id: Mapped[UUIDPK]
    organization_id: Mapped[OrgId]
    form_id: Mapped[UUIDCol]
    submission_id: Mapped[UUIDCol]
    category_id: Mapped[UUIDCol]
    serial: Mapped[int]
    signed_token: Mapped[str]
    token_hash: Mapped[str]
    issued_at: Mapped[TSNow]
    scanned_at: Mapped[TS | None]
    scanned_by: Mapped[uuid.UUID | None]


class ReconciliationAlert(Base):
    __tablename__ = "reconciliation_alerts"
    id: Mapped[UUIDPK]
    organization_id: Mapped[uuid.UUID | None]
    provider: Mapped[str]
    provider_ref: Mapped[str | None]
    payment_id: Mapped[uuid.UUID | None]
    kind: Mapped[str]
    details: Mapped[Json] = mapped_column(default=dict)
    resolved_at: Mapped[TS | None]
    resolved_by: Mapped[uuid.UUID | None]
    created_at: Mapped[TSNow]
