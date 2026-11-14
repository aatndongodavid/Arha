from __future__ import annotations

import uuid
from datetime import date

from sqlalchemy.orm import Mapped, mapped_column

from arha.db.base import Base
from arha.db.types import TS, UUIDPK, Json, OrgId, TSNow, UUIDCol


class Form(Base):
    __tablename__ = "forms"
    id: Mapped[UUIDPK]
    organization_id: Mapped[OrgId]
    folder_id: Mapped[uuid.UUID | None]
    title: Mapped[str]
    draft_schema: Mapped[Json]
    draft_revision: Mapped[int] = mapped_column(default=0)
    status: Mapped[str] = mapped_column(default="draft")
    short_code: Mapped[str]
    current_version_id: Mapped[uuid.UUID | None]
    closes_at: Mapped[TS | None]
    max_responses: Mapped[int | None]
    retention_days: Mapped[int | None]
    allow_embed: Mapped[bool] = mapped_column(default=False)
    publish_block_reason: Mapped[str | None]
    created_by: Mapped[UUIDCol]
    created_at: Mapped[TSNow]
    updated_at: Mapped[TSNow]
    deleted_at: Mapped[TS | None]


class FormVersion(Base):
    __tablename__ = "form_versions"
    id: Mapped[UUIDPK]
    organization_id: Mapped[OrgId]
    form_id: Mapped[UUIDCol]
    number: Mapped[int]
    schema: Mapped[Json]
    schema_hash: Mapped[str]
    published_by: Mapped[UUIDCol]
    published_at: Mapped[TSNow]


class FormFunnel(Base):
    __tablename__ = "form_funnel"
    organization_id: Mapped[OrgId]
    form_id: Mapped[uuid.UUID] = mapped_column(primary_key=True)
    day: Mapped[date] = mapped_column(primary_key=True)
    step: Mapped[str] = mapped_column(primary_key=True)
    value: Mapped[int] = mapped_column(default=0)
