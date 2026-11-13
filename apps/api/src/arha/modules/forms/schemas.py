from __future__ import annotations

import uuid
from datetime import datetime
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field


class _In(BaseModel):
    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)


class FormCreateIn(_In):
    title: str = Field(min_length=1, max_length=200)
    folder_id: uuid.UUID | None = None
    template: str | None = Field(default=None, max_length=64)
    locale: Literal["fr", "en"] = "fr"


class FormUpdateIn(_In):
    title: str | None = Field(default=None, min_length=1, max_length=200)
    folder_id: uuid.UUID | None = None
    move_to_root: bool = False
    closes_at: datetime | None = None
    max_responses: int | None = Field(default=None, gt=0, le=10_000_000)
    retention_days: int | None = Field(default=None, gt=0, le=3650)
    allow_embed: bool | None = None


class DraftIn(BaseModel):
    model_config = ConfigDict(extra="forbid")
    schema_: dict[str, Any] = Field(alias="schema")
    revision: int = Field(ge=0)


class ReviewIn(_In):
    message: str | None = Field(default=None, max_length=2000)


class IssueOut(BaseModel):
    severity: str
    code: str
    target: str | None
    detail: str | None


class FormSummary(BaseModel):
    id: uuid.UUID
    title: str
    status: str
    short_code: str
    folder_id: uuid.UUID | None
    updated_at: datetime
    responses: int
    public_url: str


class FormOut(FormSummary):
    draft_schema: dict[str, Any]
    draft_revision: int
    current_version: int | None
    closes_at: datetime | None
    max_responses: int | None
    retention_days: int | None
    allow_embed: bool
    publish_block_reason: str | None
    has_unpublished_changes: bool


class VersionOut(BaseModel):
    id: uuid.UUID
    number: int
    published_at: datetime
    published_by: uuid.UUID
    current: bool


class PublishOut(BaseModel):
    version: int
    public_url: str
    warnings: list[IssueOut]


class TemplateOut(BaseModel):
    code: str
    title: dict[str, str]
    description: dict[str, str]
    category: str
    schema_: dict[str, Any] = Field(serialization_alias="schema")
