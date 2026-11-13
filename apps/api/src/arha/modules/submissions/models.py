from __future__ import annotations

import uuid

from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column

from arha.db.base import Base
from arha.db.types import TS, UUIDPK, Json, OrgId, TSNow, UUIDCol


class Submission(Base):
    __tablename__ = "submissions"
    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True)
    organization_id: Mapped[OrgId]
    form_id: Mapped[UUIDCol]
    form_version_id: Mapped[UUIDCol]
    answers: Mapped[Json] = mapped_column(default=dict)
    computed: Mapped[Json] = mapped_column(default=dict)
    status: Mapped[str] = mapped_column(default="new")
    is_partial: Mapped[bool] = mapped_column(default=False)
    last_field_id: Mapped[str | None]
    payment_status: Mapped[str] = mapped_column(default="none")
    amount_due: Mapped[int | None]
    currency: Mapped[str | None]
    locale: Mapped[str] = mapped_column(default="fr")
    source: Mapped[str | None]
    hidden: Mapped[Json] = mapped_column(default=dict)
    consent_version: Mapped[str | None]
    resume_code_hash: Mapped[str | None]
    resume_expires_at: Mapped[TS | None]
    over_quota: Mapped[bool] = mapped_column(default=False)
    started_at: Mapped[TSNow]
    submitted_at: Mapped[TS | None]
    anonymized_at: Mapped[TS | None]
    deleted_at: Mapped[TS | None]


class SubmissionEvent(Base):
    __tablename__ = "submission_events"
    id: Mapped[UUIDPK]
    organization_id: Mapped[OrgId]
    submission_id: Mapped[UUIDCol]
    actor_id: Mapped[uuid.UUID | None]
    from_status: Mapped[str | None]
    to_status: Mapped[str]
    created_at: Mapped[TSNow]


class IdempotencyKey(Base):
    __tablename__ = "idempotency_keys"
    organization_id: Mapped[uuid.UUID] = mapped_column(primary_key=True)
    key: Mapped[str] = mapped_column(primary_key=True)
    scope: Mapped[str] = mapped_column(primary_key=True)
    request_hash: Mapped[str]
    response: Mapped[Json | None]
    status_code: Mapped[int | None]
    created_at: Mapped[TSNow]
