from __future__ import annotations

import uuid

from sqlalchemy.orm import Mapped, mapped_column

from arha.db.base import Base
from arha.db.types import TS, UUIDPK, Json, OrgId, TSNow, UUIDCol


class AuditEvent(Base):
    __tablename__ = "audit_events"
    id: Mapped[UUIDPK]
    organization_id: Mapped[uuid.UUID | None]
    actor_id: Mapped[uuid.UUID | None]
    action: Mapped[str]
    target_type: Mapped[str | None]
    target_id: Mapped[str | None]
    ip_hash: Mapped[str | None]
    metadata_: Mapped[Json] = mapped_column("metadata", default=dict)
    created_at: Mapped[TSNow]
    previous_hash: Mapped[str | None]
    hash: Mapped[str]


class AbuseReport(Base):
    __tablename__ = "abuse_reports"
    id: Mapped[UUIDPK]
    form_id: Mapped[UUIDCol]
    organization_id: Mapped[OrgId]
    reason: Mapped[str]
    details: Mapped[str | None]
    reporter_contact_enc: Mapped[str | None]
    snapshot: Mapped[Json]
    status: Mapped[str] = mapped_column(default="open")
    decided_by: Mapped[uuid.UUID | None]
    decided_at: Mapped[TS | None]
    created_at: Mapped[TSNow]


class PublicationReview(Base):
    __tablename__ = "publication_reviews"
    id: Mapped[UUIDPK]
    organization_id: Mapped[OrgId]
    form_id: Mapped[UUIDCol]
    matches: Mapped[Json]
    message: Mapped[str | None]
    status: Mapped[str] = mapped_column(default="open")
    decided_by: Mapped[uuid.UUID | None]
    decided_at: Mapped[TS | None]
    created_at: Mapped[TSNow]


class VerificationRequest(Base):
    __tablename__ = "verification_requests"
    id: Mapped[UUIDPK]
    organization_id: Mapped[OrgId]
    document_key: Mapped[str]
    document_type: Mapped[str]
    status: Mapped[str] = mapped_column(default="pending")
    note: Mapped[str | None]
    decided_by: Mapped[uuid.UUID | None]
    decided_at: Mapped[TS | None]
    created_at: Mapped[TSNow]


class StoredFile(Base):
    __tablename__ = "files"
    id: Mapped[UUIDPK]
    organization_id: Mapped[OrgId]
    key: Mapped[str]
    content_type: Mapped[str]
    size_bytes: Mapped[int]
    scan_status: Mapped[str] = mapped_column(default="pending")
    purpose: Mapped[str]
    created_at: Mapped[TSNow]
