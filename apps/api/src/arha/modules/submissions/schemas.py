from __future__ import annotations

import uuid
from datetime import datetime
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator


class SubmissionIn(BaseModel):
    model_config = ConfigDict(extra="forbid")
    id: uuid.UUID
    form_version_id: uuid.UUID
    answers: dict[str, Any] = Field(default_factory=dict)
    hidden: dict[str, str] = Field(default_factory=dict)
    locale: Literal["fr", "en"] = "fr"
    partial: bool = False
    last_field_id: str | None = Field(default=None, max_length=40)
    consent_version: str | None = Field(default=None, max_length=32)

    @field_validator("id")
    @classmethod
    def _uuid7(cls, v: uuid.UUID) -> uuid.UUID:
        if v.version != 7:
            raise ValueError("submission id must be a UUIDv7")
        return v

    @field_validator("answers")
    @classmethod
    def _size(cls, v: dict[str, Any]) -> dict[str, Any]:
        if len(v) > 500:
            raise ValueError("too many answers")
        return v

    @field_validator("hidden")
    @classmethod
    def _hidden(cls, v: dict[str, str]) -> dict[str, str]:
        if len(v) > 20 or any(len(k) > 32 or len(x) > 500 for k, x in v.items()):
            raise ValueError("hidden parameters too large")
        return v


class SubmissionResult(BaseModel):
    id: uuid.UUID
    status: str
    payment_required: bool
    payment_status: str
    amount: int
    currency: str | None
    platform_fee: int = 0
    estimated_provider_fee: int = 0
    total_to_pay: int = 0
    line_items: list[dict[str, Any]] = Field(default_factory=list)
    ending: dict[str, Any] = Field(default_factory=dict)


class ResumeIn(BaseModel):
    model_config = ConfigDict(extra="forbid")
    code: str = Field(min_length=6, max_length=6)


class ResumeCodeOut(BaseModel):
    code: str
    expires_at: datetime


class ReportIn(BaseModel):
    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)
    reason: Literal["phishing", "scam", "inappropriate", "other"]
    details: str | None = Field(default=None, max_length=2000)
    contact: str | None = Field(default=None, max_length=254)


class FunnelIn(BaseModel):
    model_config = ConfigDict(extra="forbid")
    step: Literal["start"] = "start"
    field_id: str | None = Field(default=None, max_length=40)


class SubmissionRow(BaseModel):
    id: uuid.UUID
    status: str
    is_partial: bool
    last_field_id: str | None
    payment_status: str
    amount_due: int | None
    currency: str | None
    locale: str
    source: str | None
    answers: dict[str, Any]
    computed: dict[str, Any]
    form_version_id: uuid.UUID
    started_at: datetime
    submitted_at: datetime | None
    anonymized: bool


class SubmissionPage(BaseModel):
    items: list[SubmissionRow]
    next_cursor: str | None
    total: int


class StatusIn(BaseModel):
    model_config = ConfigDict(extra="forbid")
    status: Literal["new", "in_progress", "done", "rejected"]


class BulkIn(BaseModel):
    model_config = ConfigDict(extra="forbid")
    ids: list[uuid.UUID] = Field(min_length=1, max_length=500)
