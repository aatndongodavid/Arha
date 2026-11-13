"""Submissions: idempotent public intake, partial saves, resume codes, status workflow (F-PUB, F-REP)."""

from __future__ import annotations

import base64
import json
import uuid
from datetime import datetime, timedelta
from typing import Any

from sqlalchemy import func, or_, select, text
from sqlalchemy.ext.asyncio import AsyncSession

from arha.core import clock, jobs
from arha.core.errors import AppError, NotFound
from arha.core.ids import uuid7
from arha.core.plans import get_plans
from arha.core.security import sha256_hex, short_code
from arha.modules.logic.engine import evaluate
from arha.modules.submissions.models import Submission, SubmissionEvent

TRANSITIONS = {
    "new": {"in_progress", "done", "rejected"},
    "in_progress": {"new", "done", "rejected"},
    "done": {"in_progress", "rejected"},
    "rejected": {"new", "in_progress"},
}


async def count_by_form(db: AsyncSession, form_ids: list[uuid.UUID]) -> dict[uuid.UUID, int]:
    if not form_ids:
        return {}
    stmt = (select(Submission.form_id, func.count()).where(
        Submission.form_id.in_(form_ids), Submission.is_partial.is_(False), Submission.deleted_at.is_(None),
        Submission.submitted_at.is_not(None)).group_by(Submission.form_id))
    return {fid: int(n) for fid, n in (await db.execute(stmt)).all()}


async def completed_count(db: AsyncSession, form_id: uuid.UUID) -> int:
    return (await count_by_form(db, [form_id])).get(form_id, 0)


def availability(form: Any, org: Any, completed: int) -> str | None:
    """Return a stable reason code when the form cannot accept responses, else None."""
    if org.suspended_at is not None or form.status == "suspended" or form.deleted_at is not None:
        return "form_unavailable"
    if form.status != "published" or form.current_version_id is None:
        return "form_closed" if form.status == "closed" else "form_unavailable"
    if form.closes_at is not None and form.closes_at <= clock.now():
        return "form_closed"
    if form.max_responses is not None and completed >= form.max_responses:
        return "form_closed"
    return None


def result_of(sub: Submission, ending: dict[str, Any] | None = None) -> dict[str, Any]:
    computed = sub.computed or {}
    return {"id": sub.id, "status": sub.status, "payment_required": sub.payment_status in (
        "pending_payment", "pending", "failed", "expired"), "payment_status": sub.payment_status,
            "amount": sub.amount_due or 0, "currency": sub.currency, "line_items": computed.get("line_items", []),
            "platform_fee": computed.get("platform_fee", 0),
            "estimated_provider_fee": computed.get("estimated_provider_fee", 0),
            "total_to_pay": computed.get("total_to_pay", sub.amount_due or 0), "ending": ending or {}}


def fee_breakdown(org: Any, amount: int, fee_bearer: str, provider: str) -> dict[str, int]:
    """Arha commission (fee_bps, rounded up) and estimated aggregator fee (master prompt 9.5)."""
    from arha.core.plans import get_countries

    fee_bps = get_plans().plans[org.plan_code].fee_bps
    platform_fee = -(-amount * fee_bps // 10_000) if amount else 0
    provider_bps = get_countries().providers[provider].estimated_fee_bps if provider in get_countries(
    ).providers else 0
    est = -(-amount * provider_bps // 10_000) if amount else 0
    total = amount + platform_fee + est if fee_bearer == "payer" else amount
    return {"platform_fee": platform_fee, "estimated_provider_fee": est, "total_to_pay": total}


async def get_for_update(db: AsyncSession, sub_id: uuid.UUID) -> Submission | None:
    stmt = select(Submission).where(Submission.id == sub_id).with_for_update()
    return (await db.execute(stmt)).scalar_one_or_none()


async def intake(db: AsyncSession, *, form: Any, org: Any, version: Any, payload: Any,
                 provider: str) -> tuple[dict[str, Any], int]:
    """Create or update a submission. Idempotent by the browser generated UUIDv7 (rule 5)."""
    existing = await get_for_update(db, payload.id)
    if existing is not None:
        if existing.form_id != form.id:
            raise NotFound("submission_not_found")
        if existing.submitted_at is not None and not existing.is_partial:
            return result_of(existing, _ending(version.schema)), 200  # replay returns the initial result

    if version.form_id != form.id:
        raise AppError("submission_version_mismatch", 409)
    schema: dict[str, Any] = version.schema
    hidden = dict(payload.hidden)
    result = evaluate(schema, payload.answers, hidden)
    source = hidden.get("source") or hidden.get("utm_source")

    sub = existing or Submission(id=payload.id, form_id=form.id, form_version_id=version.id,
                                 started_at=clock.now())
    sub.form_version_id = version.id
    sub.locale = payload.locale
    sub.hidden = {k: v for k, v in hidden.items()}
    sub.source = source[:64] if source else None

    if payload.partial:
        # F-REP-03 and F-PUB-03: keep what was typed, never validate a draft.
        sub.answers = result.clean_answers
        sub.is_partial = True
        sub.last_field_id = payload.last_field_id
        if existing is None:
            db.add(sub)
            from arha.modules.forms.service import bump_funnel
            await bump_funnel(db, form.id, "start")
        await db.flush()
        return {"id": sub.id, "status": "draft", "payment_required": False, "payment_status": "none",
                "amount": 0, "currency": None}, 202

    if result.errors:
        raise AppError("submission_invalid", 422, extra={"errors": result.errors})
    await _check_files(db, form.id, schema, result.clean_answers)
    settings = schema.get("settings") or {}
    payments = settings.get("payments") or {}
    from arha.modules.billing.service import admit_response

    sub.over_quota = await admit_response(db, org)
    sub.answers = result.clean_answers
    sub.is_partial = False
    sub.last_field_id = None
    sub.submitted_at = clock.now()
    sub.consent_version = payload.consent_version or (settings.get("consent") or {}).get("textVersion")
    sub.resume_code_hash = None
    computed: dict[str, Any] = {"variables": result.variables, "line_items": result.line_items,
                                "amount": result.amount, "path": result.path}
    if result.amount > 0:
        currency = payments.get("currency", org.currency)
        computed.update(fee_breakdown(org, result.amount, payments.get("feeBearer", "org"), provider))
        sub.payment_status = "pending_payment"
        sub.amount_due = result.amount
        sub.currency = currency
    else:
        sub.payment_status = "none"
        sub.amount_due = None
    sub.computed = computed
    if existing is None:
        db.add(sub)
    await db.flush()
    from arha.modules.forms.service import bump_funnel
    await bump_funnel(db, form.id, "complete")
    if sub.payment_status == "none":
        jobs.enqueue(db, "submissions.completed", org_id=str(org.id), submission_id=str(sub.id))
    return result_of(sub, _ending(schema)), 201


def _ending(schema: dict[str, Any]) -> dict[str, Any]:
    return (schema.get("settings") or {}).get("ending") or {}


async def _check_files(db: AsyncSession, form_id: uuid.UUID, schema: dict[str, Any], answers: dict[str, Any]) -> None:
    keys = [k for p in schema.get("pages", []) for b in p.get("blocks", []) if b["type"] == "file_upload"
            for k in (answers.get(b["id"]) or [])]
    if not keys:
        return
    found = (await db.execute(text("select count(*) from files where key = any(:k) and purpose = 'response'"),
                              {"k": keys})).scalar_one()
    if found != len(set(keys)) or any(f"/{form_id}/" not in k for k in keys):
        raise AppError("submission_invalid", 422, extra={"errors": [{"field": "_files", "code": "invalid_file"}]})


async def issue_resume_code(db: AsyncSession, sub: Submission) -> tuple[str, datetime]:
    code = short_code(6)
    sub.resume_code_hash = sha256_hex(f"{sub.form_id}:{code}")
    sub.resume_expires_at = clock.now() + timedelta(days=get_plans().resume_code_days)
    return code, sub.resume_expires_at


def resume_hash(form_id: uuid.UUID, code: str) -> str:
    return sha256_hex(f"{form_id}:{code.upper()}")


async def find_by_resume(db: AsyncSession, form_id: uuid.UUID, code: str) -> Submission:
    stmt = select(Submission).where(Submission.resume_code_hash == resume_hash(form_id, code),
                                    Submission.form_id == form_id)
    sub = (await db.execute(stmt)).scalar_one_or_none()
    if sub is None or not sub.is_partial or (sub.resume_expires_at and sub.resume_expires_at < clock.now()):
        raise AppError("resume_code_invalid", 404)
    return sub


# ------------------------------------------------------------------ organisation side


def _encode_cursor(at: datetime, sid: uuid.UUID) -> str:
    return base64.urlsafe_b64encode(json.dumps([at.isoformat(), str(sid)]).encode()).decode()


def _decode_cursor(cursor: str) -> tuple[datetime, uuid.UUID]:
    try:
        at, sid = json.loads(base64.urlsafe_b64decode(cursor.encode()))
        return datetime.fromisoformat(at), uuid.UUID(sid)
    except (ValueError, TypeError) as exc:
        raise AppError("validation_failed", 422) from exc


async def page(db: AsyncSession, *, form_id: uuid.UUID, status: str | None, payment_status: str | None,
               q: str | None, include_partial: bool, cursor: str | None, limit: int
               ) -> tuple[list[Submission], str | None, int]:
    """Server side cursor pagination ordered by (started_at desc, id desc) (F-REP-01)."""
    base = select(Submission).where(Submission.form_id == form_id, Submission.deleted_at.is_(None))
    if not include_partial:
        base = base.where(Submission.is_partial.is_(False))
    if status:
        base = base.where(Submission.status == status)
    if payment_status:
        base = base.where(Submission.payment_status == payment_status)
    if q:
        needle = f"%{q.replace('%', '').replace('_', '')}%"
        base = base.where(or_(Submission.answers.cast(text("text")).ilike(needle),  # type: ignore[arg-type]
                              func.cast(Submission.id, text("text")).ilike(needle)))  # type: ignore[arg-type]
    total = int((await db.execute(select(func.count()).select_from(base.subquery()))).scalar_one())
    stmt = base
    if cursor:
        at, sid = _decode_cursor(cursor)
        stmt = stmt.where(func.row(Submission.started_at, Submission.id) < func.row(at, sid))
    stmt = stmt.order_by(Submission.started_at.desc(), Submission.id.desc()).limit(limit + 1)
    rows = list((await db.execute(stmt)).scalars())
    nxt = _encode_cursor(rows[limit - 1].started_at, rows[limit - 1].id) if len(rows) > limit else None
    return rows[:limit], nxt, total


async def get(db: AsyncSession, form_id: uuid.UUID, sub_id: uuid.UUID) -> Submission:
    sub = await db.get(Submission, sub_id)
    if sub is None or sub.form_id != form_id or sub.deleted_at is not None:
        raise NotFound("submission_not_found")
    return sub


async def set_status(db: AsyncSession, sub: Submission, status: str, actor_id: uuid.UUID) -> Submission:
    if status == sub.status:
        return sub
    if status not in TRANSITIONS.get(sub.status, set()):
        raise AppError("invalid_status_transition", 409)
    db.add(SubmissionEvent(id=uuid7(), submission_id=sub.id, actor_id=actor_id, from_status=sub.status,
                           to_status=status))
    sub.status = status
    return sub


async def history(db: AsyncSession, sub_id: uuid.UUID) -> list[SubmissionEvent]:
    stmt = select(SubmissionEvent).where(SubmissionEvent.submission_id == sub_id).order_by(
        SubmissionEvent.created_at)
    return list((await db.execute(stmt)).scalars())


def identifying_fields(schema: dict[str, Any]) -> set[str]:
    return {b["id"] for p in schema.get("pages", []) for b in p.get("blocks", [])
            if b.get("identifying") or b["type"] in ("email", "phone", "signature", "file_upload")}


async def anonymize(db: AsyncSession, sub: Submission, schema: dict[str, Any]) -> None:
    """F-REP-07: remove identifying fields, keep the rest for statistics."""
    ids = identifying_fields(schema)
    sub.answers = {k: v for k, v in (sub.answers or {}).items() if k not in ids}
    sub.hidden = {}
    sub.resume_code_hash = None
    sub.anonymized_at = clock.now()


async def delete(db: AsyncSession, sub: Submission) -> None:
    sub.answers = {}
    sub.hidden = {}
    sub.computed = {k: v for k, v in (sub.computed or {}).items() if k in ("amount",)}
    sub.deleted_at = clock.now()
