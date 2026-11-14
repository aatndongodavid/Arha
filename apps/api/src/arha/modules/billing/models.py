from __future__ import annotations

import uuid
from typing import Any

from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column

from arha.db.base import Base
from arha.db.types import TS, UUIDPK, Money, OrgId, TSNow


class Subscription(Base):
    __tablename__ = "subscriptions"
    id: Mapped[UUIDPK]
    organization_id: Mapped[OrgId]
    plan_code: Mapped[str]
    billing_period: Mapped[str]
    amount: Mapped[Money]
    currency: Mapped[str]
    period_start: Mapped[TS | None]
    period_end: Mapped[TS | None]
    status: Mapped[str]
    pioneer: Mapped[bool] = mapped_column(default=False)
    discount_bps: Mapped[int] = mapped_column(default=0)
    payment_id: Mapped[uuid.UUID | None]
    reminded_at: Mapped[TS | None]
    created_at: Mapped[TSNow]


class Invoice(Base):
    __tablename__ = "invoices"
    id: Mapped[UUIDPK]
    organization_id: Mapped[OrgId]
    number: Mapped[str]
    kind: Mapped[str] = mapped_column(default="subscription")
    amount: Mapped[Money]
    currency: Mapped[str]
    payment_id: Mapped[uuid.UUID | None]
    lines: Mapped[list[Any]] = mapped_column(JSONB, default=list)
    issued_at: Mapped[TSNow]
    pdf_key: Mapped[str | None]


class UsageCounter(Base):
    __tablename__ = "usage_counters"
    organization_id: Mapped[uuid.UUID] = mapped_column(primary_key=True)
    metric: Mapped[str] = mapped_column(primary_key=True)
    period: Mapped[str] = mapped_column(primary_key=True)
    value: Mapped[int] = mapped_column(default=0)
    alerted_at: Mapped[TS | None]


class StudentPass(Base):
    """Pass Mémoire (F-FAC-06): one payment, 120 days, never renewed automatically (E-04)."""

    __tablename__ = "student_passes"
    id: Mapped[UUIDPK]
    organization_id: Mapped[OrgId]
    user_id: Mapped[uuid.UUID]
    institution: Mapped[str]
    level: Mapped[str]
    amount: Mapped[Money]
    currency: Mapped[str]
    ambassador_code: Mapped[str | None]
    status: Mapped[str] = mapped_column(default="pending_payment")
    starts_at: Mapped[TS | None]
    ends_at: Mapped[TS | None]
    payment_id: Mapped[uuid.UUID | None]
    created_at: Mapped[TSNow]
