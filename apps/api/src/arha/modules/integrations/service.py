"""Outgoing signed webhooks (F-REP-06, S-11) and Google Sheets sync (F-REP-05)."""

from __future__ import annotations

import hashlib
import hmac
import json
import time
import uuid
from datetime import timedelta
from typing import Any

import httpx
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from arha.core import clock, jobs
from arha.core.crypto import decrypt, encrypt
from arha.core.features import has_feature
from arha.core.ids import uuid7
from arha.core.security import new_token, sha256_hex
from arha.modules.integrations.models import WebhookDelivery, WebhookEndpoint
from arha.modules.integrations.ssrf import resolve_public

RETRY_SCHEDULE = [60, 300, 900, 3600, 3 * 3600, 6 * 3600, 12 * 3600]  # about 22 hours in total
TIMEOUT = 10.0


def signature_header(secret: str, body: bytes, timestamp: int | None = None) -> str:
    ts = timestamp or int(time.time())
    mac = hmac.new(secret.encode(), f"{ts}.".encode() + body, hashlib.sha256).hexdigest()
    return f"t={ts},v1={mac}"


def verify_signature(secret: str, body: bytes, header: str, tolerance: int = 300) -> bool:
    """Reference implementation published for integrators (5 minute tolerance)."""
    try:
        parts = dict(p.split("=", 1) for p in header.split(","))
        ts = int(parts["t"])
    except (ValueError, KeyError):
        return False
    if abs(time.time() - ts) > tolerance:
        return False
    expected = signature_header(secret, body, ts).split("v1=")[1]
    return hmac.compare_digest(expected, parts.get("v1", ""))


async def create_endpoint(db: AsyncSession, url: str, form_id: uuid.UUID | None) -> tuple[WebhookEndpoint, str]:
    await resolve_public(url)
    secret = f"whsec_{new_token(24)}"
    ep = WebhookEndpoint(id=uuid7(), url=url, form_id=form_id, secret_enc=encrypt(secret))
    db.add(ep)
    await db.flush()
    return ep, secret


def submission_payload(sub: Any, form_id: uuid.UUID) -> dict[str, Any]:
    return {"id": str(sub.id), "form_id": str(form_id), "submitted_at": sub.submitted_at.isoformat()
            if sub.submitted_at else None, "status": sub.status, "payment_status": sub.payment_status,
            "amount": sub.amount_due, "currency": sub.currency, "locale": sub.locale, "answers": sub.answers or {},
            "computed": {k: v for k, v in (sub.computed or {}).items() if k in ("variables", "line_items", "amount")}}


async def emit_event(db: AsyncSession, event: str, *, form_id: uuid.UUID, submission: Any) -> int:
    from arha.modules.orgs.service import get_org

    org = await get_org(db, submission.organization_id)
    if not has_feature(org, "webhooks"):
        return 0
    endpoints = (await db.execute(select(WebhookEndpoint).where(
        WebhookEndpoint.active.is_(True)))).scalars()
    count = 0
    event_id = uuid7()
    for ep in endpoints:
        if ep.form_id not in (None, form_id) or event not in ep.events:
            continue
        payload = {"id": str(event_id), "type": event, "created_at": clock.now().isoformat(),
                   "data": submission_payload(submission, form_id)}
        delivery = WebhookDelivery(id=uuid7(), endpoint_id=ep.id, event=event, event_id=event_id, payload=payload,
                                   payload_hash=sha256_hex(json.dumps(payload, sort_keys=True)),
                                   next_retry_at=clock.now())
        db.add(delivery)
        await db.flush()
        jobs.enqueue(db, "integrations.deliver", org_id=str(submission.organization_id),
                     delivery_id=str(delivery.id))
        count += 1
    return count


async def deliver(db: AsyncSession, delivery: WebhookDelivery, *, transport: httpx.AsyncBaseTransport | None = None
                  ) -> bool:
    ep = await db.get(WebhookEndpoint, delivery.endpoint_id)
    if ep is None or not ep.active or delivery.delivered_at or delivery.failed_at:
        return False
    body = json.dumps(delivery.payload, separators=(",", ":"), ensure_ascii=False).encode()
    delivery.attempt += 1
    try:
        if transport is None:
            await resolve_public(ep.url)  # re-checked at each attempt: DNS can change
        async with httpx.AsyncClient(timeout=TIMEOUT, follow_redirects=False, transport=transport) as client:
            resp = await client.post(ep.url, content=body, headers={
                "Content-Type": "application/json", "User-Agent": "Arha-Webhooks/1.0",
                "Arha-Event": delivery.event, "Arha-Delivery": str(delivery.id),
                "Arha-Signature": signature_header(decrypt(ep.secret_enc), body)})
        delivery.status_code = resp.status_code
        ok = 200 <= resp.status_code < 300
        delivery.error = None if ok else f"http_{resp.status_code}"
    except Exception as exc:  # noqa: BLE001 - every failure is recorded and retried
        ok = False
        delivery.error = type(exc).__name__[:100]
    if ok:
        delivery.delivered_at = clock.now()
        delivery.next_retry_at = None
        return True
    if delivery.attempt > len(RETRY_SCHEDULE):
        delivery.failed_at = clock.now()
        delivery.next_retry_at = None
    else:
        delay = RETRY_SCHEDULE[delivery.attempt - 1]
        delivery.next_retry_at = clock.now() + timedelta(seconds=delay)
        jobs.enqueue(db, "integrations.deliver", schedule_in=delay, org_id=str(delivery.organization_id),
                     delivery_id=str(delivery.id))
    return False
