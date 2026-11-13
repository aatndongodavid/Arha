"""Idempotency-Key handling (rule 5, master prompt section 13). Keys are kept 24 hours."""

from __future__ import annotations

import json
from datetime import timedelta
from typing import Any

from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from arha.core import clock
from arha.core.errors import AppError
from arha.core.security import sha256_hex

TTL = timedelta(hours=24)


def require_key(value: str | None) -> str:
    if not value or not 8 <= len(value) <= 128:
        raise AppError("idempotency_key_required", 400)
    return value


def request_hash(body: Any) -> str:
    return sha256_hex(json.dumps(body, sort_keys=True, default=str, separators=(",", ":")))


async def lookup(db: AsyncSession, scope: str, key: str, body_hash: str) -> dict[str, Any] | None:
    """Return the stored response for a replay, raise on key reuse with another body, None if new."""
    row = (await db.execute(text(
        "select request_hash, response, status_code, created_at from idempotency_keys "
        "where organization_id = app_org() and scope = :s and key = :k for update"), {"s": scope, "k": key})).first()
    if row is None or row.created_at < clock.now() - TTL:
        return None
    if row.request_hash != body_hash:
        raise AppError("idempotency_key_reused", 422)
    return {"response": row.response, "status_code": row.status_code} if row.response is not None else None


async def store(db: AsyncSession, scope: str, key: str, body_hash: str, response: dict[str, Any],
                status_code: int) -> None:
    await db.execute(text(
        "insert into idempotency_keys (organization_id, key, scope, request_hash, response, status_code) "
        "values (app_org(), :k, :s, :h, cast(:r as jsonb), :c) on conflict (organization_id, scope, key) do update "
        "set response = excluded.response, status_code = excluded.status_code, request_hash = excluded.request_hash, "
        "created_at = now()"),
        {"k": key, "s": scope, "h": body_hash, "r": json.dumps(response, default=str), "c": status_code})
