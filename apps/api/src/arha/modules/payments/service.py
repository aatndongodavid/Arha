"""Mobile Money collection on the organisation's connected account (rule 1, F-PAY-01..10, S-19).

Arha never holds third party funds: charges settle on the organisation's connected account and the
aggregator deducts Arha's platform fee at collection time.
"""

from __future__ import annotations

import uuid
from datetime import timedelta
from typing import Any

import phonenumbers
import structlog
from sqlalchemy import func, select, text
from sqlalchemy.ext.asyncio import AsyncSession

from arha.core import clock, jobs
from arha.core.crypto import sign_compact
from arha.core.errors import AppError, NotFound
from arha.core.ids import uuid7
from arha.core.plans import get_countries, get_plans
from arha.core.security import keyed_hash, sha256_hex
from arha.db.session import app_tx
from arha.modules.payments.adapters.base import ChargeRequest, KycPayload, OrgRef, ProviderError
from arha.modules.payments.adapters.registry import get_provider, resolve_code
from arha.modules.payments.models import Payment, PaymentAccount, ReconciliationAlert, Ticket, TicketCategory
from arha.modules.trust import service as trust
from arha.settings import get_settings

log = structlog.get_logger()

TERMINAL = {"succeeded", "failed", "expired", "refunded"}
TRANSITIONS: dict[str, set[str]] = {
    "created": {"pending", "failed", "expired", "succeeded"},
    "pending": {"succeeded", "failed", "expired"},
    "succeeded": {"refunded"},
    "failed": set(),
    "expired": {"succeeded"},  # a late confirmation of real money is accepted and alerted, never lost
    "refunded": set(),
}
POLL_DELAYS = [90, 60, 90, 120, 180, 240, 300]  # seconds, cumulative about 18 minutes
# Cameroon mobile prefixes (ART numbering plan). VERIFY periodically: operators reassign ranges.
_MTN = ("67", "650", "651", "652", "653", "654", "680", "681", "682", "683", "684")
_ORANGE = ("69", "655", "656", "657", "658", "659", "686", "687", "688", "689")


class InvalidTransition(AppError):
    def __init__(self, current: str, target: str) -> None:
        super().__init__("invalid_status_transition", 409, extra={"from": current, "to": target})


# ------------------------------------------------------------------ phone numbers


def normalize_msisdn(raw: str, country: str = "CM") -> tuple[str, str]:
    """Return (E.164 number, detected operator). The PIN is never requested (rule 3)."""
    try:
        num = phonenumbers.parse(raw, country)
    except phonenumbers.NumberParseException as exc:
        raise AppError("payment_invalid_phone", 422) from exc
    if not phonenumbers.is_valid_number(num) or phonenumbers.number_type(num) not in (
            phonenumbers.PhoneNumberType.MOBILE, phonenumbers.PhoneNumberType.FIXED_LINE_OR_MOBILE):
        raise AppError("payment_invalid_phone", 422)
    e164 = phonenumbers.format_number(num, phonenumbers.PhoneNumberFormat.E164)
    national = e164[4:] if e164.startswith("+237") else ""
    operator = "mtn" if national.startswith(_MTN) else "orange" if national.startswith(_ORANGE) else "auto"
    return e164, operator


# ------------------------------------------------------------------ accounts and publication checks


async def get_account(db: AsyncSession, provider: str) -> PaymentAccount | None:
    stmt = select(PaymentAccount).where(PaymentAccount.provider == provider)
    return (await db.execute(stmt)).scalar_one_or_none()


async def ensure_can_collect(db: AsyncSession, schema: dict[str, Any]) -> None:
    provider = resolve_code(((schema.get("settings") or {}).get("payments") or {}).get("provider"))
    if provider == "fake":
        return
    account = await get_account(db, provider)
    if account is None or account.status != "verified":
        raise AppError("payment_account_required", 422)


async def connect_account(db: AsyncSession, org: Any, provider_code: str, owner_email: str) -> PaymentAccount:
    provider = get_provider(provider_code)
    account = await get_account(db, provider.code)
    try:
        if account is None:
            result = await provider.create_connected_account(
                OrgRef(id=str(org.id), name=org.name, country=org.country),
                KycPayload(email=owner_email, business_name=org.name))
            account = PaymentAccount(id=uuid7(), provider=provider.code)
            db.add(account)
        else:
            result = await provider.get_connected_account(account.provider_account_id or "")
    except ProviderError as exc:
        raise AppError("payment_provider_unavailable", 503) from exc
    account.provider_account_id = result.provider_account_id
    account.status = result.status
    account.onboarding_url = result.onboarding_url
    account.updated_at = clock.now()
    await db.flush()
    return account


# ------------------------------------------------------------------ tickets


async def sync_ticket_categories(db: AsyncSession, form_id: uuid.UUID, schema: dict[str, Any]) -> None:
    for page in schema.get("pages", []):
        for block in page.get("blocks", []):
            if block["type"] != "ticket_choice":
                continue
            for opt in block.get("options") or []:
                name = (opt.get("label") or {}).get(schema.get("defaultLocale", "fr")) or opt["id"]
                await db.execute(text(
                    "insert into ticket_categories (id, organization_id, form_id, block_id, option_id, name, quota, "
                    "price) values (:id, app_org(), :f, :b, :o, :n, :q, :p) on conflict (form_id, block_id, option_id) "
                    "do update set name = excluded.name, quota = excluded.quota, price = excluded.price"),
                    {"id": uuid7(), "f": form_id, "b": block["id"], "o": opt["id"], "n": name[:200],
                     "q": opt.get("quota"), "p": int(opt.get("price", 0))})


async def tickets_remaining(db: AsyncSession, form_id: uuid.UUID) -> dict[str, dict[str, int | None]]:
    rows = (await db.execute(select(TicketCategory).where(TicketCategory.form_id == form_id))).scalars()
    out: dict[str, dict[str, int | None]] = {}
    for c in rows:
        out.setdefault(c.block_id, {})[c.option_id] = (
            None if c.quota is None else max(0, c.quota - c.issued - c.reserved))
    return out


def _ticket_lines(sub: Any, schema: dict[str, Any]) -> list[tuple[str, str, int]]:
    ticket_blocks = {b["id"] for p in schema.get("pages", []) for b in p.get("blocks", [])
                     if b["type"] == "ticket_choice"}
    return [(li["block"], li["option"], int(li["quantity"])) for li in (sub.computed or {}).get("line_items", [])
            if li.get("block") in ticket_blocks and li.get("quantity")]


async def _reserve(db: AsyncSession, form_id: uuid.UUID, lines: list[tuple[str, str, int]]) -> list[dict[str, Any]]:
    """Lock each category row and reserve seats. Guarantees the quota is never exceeded (F-PAY-07)."""
    reserved: list[dict[str, Any]] = []
    for block_id, option_id, qty in sorted(lines):  # stable lock order avoids deadlocks
        cat = (await db.execute(select(TicketCategory).where(
            TicketCategory.form_id == form_id, TicketCategory.block_id == block_id,
            TicketCategory.option_id == option_id).with_for_update())).scalar_one_or_none()
        if cat is None:
            continue
        if cat.quota is not None and cat.issued + cat.reserved + qty > cat.quota:
            raise AppError("ticket_sold_out", 409, params={"name": cat.name})
        cat.reserved += qty
        reserved.append({"category_id": str(cat.id), "quantity": qty})
    return reserved


async def _release(db: AsyncSession, reservation: list[dict[str, Any]]) -> None:
    for item in sorted(reservation, key=lambda r: r["category_id"]):
        await db.execute(text("update ticket_categories set reserved = greatest(0, reserved - :q) where id = :id"),
                         {"q": item["quantity"], "id": item["category_id"]})


async def _issue(db: AsyncSession, payment: Payment, reservation: list[dict[str, Any]], form_id: uuid.UUID) -> None:
    for item in sorted(reservation, key=lambda r: r["category_id"]):
        cat = (await db.execute(select(TicketCategory).where(TicketCategory.id == uuid.UUID(item["category_id"]))
                                .with_for_update())).scalar_one()
        qty = int(item["quantity"])
        start = cat.issued
        cat.issued += qty
        cat.reserved = max(0, cat.reserved - qty)
        for serial in range(start + 1, start + qty + 1):
            tid = uuid7()
            issued_at = clock.now()
            token = sign_compact({"t": str(tid), "f": str(form_id), "c": str(cat.id), "s": serial,
                                  "i": int(issued_at.timestamp())})
            db.add(Ticket(id=tid, form_id=form_id, submission_id=payment.submission_id, category_id=cat.id,
                          serial=serial, signed_token=token, token_hash=sha256_hex(token), issued_at=issued_at))
    await db.flush()


def _reservation_of(payment: Payment) -> list[dict[str, Any]]:
    for event in payment.raw_events or []:
        if event.get("type") == "reservation":
            return list(event.get("items", []))
    return []


# ------------------------------------------------------------------ state machine


async def apply_status(db: AsyncSession, payment: Payment, target: str, *, source: str,
                       failure_reason: str | None = None) -> bool:
    """Move a payment to `target`. Returns True when the state changed. Every transition is journalled."""
    if payment.status == target:
        return False
    if target not in TRANSITIONS.get(payment.status, set()):
        log.error("payment_invalid_transition", payment_id=str(payment.id), current=payment.status, target=target,
                  source=source)
        db.add(ReconciliationAlert(id=uuid7(), organization_id=payment.organization_id, provider=payment.provider,
                                   provider_ref=payment.provider_ref, payment_id=payment.id, kind="status_mismatch",
                                   details={"from": payment.status, "to": target, "source": source}))
        return False
    previous = payment.status
    now = clock.now()
    payment.raw_events = [*(payment.raw_events or []), {"type": "transition", "from": previous, "to": target,
                                                        "source": source, "at": now.isoformat()}]
    payment.status = target
    payment.updated_at = now
    if failure_reason:
        payment.failure_reason = failure_reason[:100]
    await trust.audit(db, f"payment.{target}", org_id=payment.organization_id, actor_id=None, target_type="payment",
                      target_id=payment.id, metadata={"from": previous, "source": source})
    from arha.modules.submissions.models import Submission

    sub = await db.get(Submission, payment.submission_id) if payment.submission_id else None
    if target == "succeeded":
        if previous == "expired":
            db.add(ReconciliationAlert(id=uuid7(), organization_id=payment.organization_id, provider=payment.provider,
                                       provider_ref=payment.provider_ref, payment_id=payment.id,
                                       kind="status_mismatch", details={"late_success": True}))
        payment.receipt_number = await _receipt_number(db)
        if sub is not None:
            sub.payment_status = "paid"
            await _issue(db, payment, _reservation_of(payment) if previous != "expired" else [], sub.form_id)
        if payment.purpose == "submission" and not get_provider(payment.provider).supports_platform_fee:
            from arha.modules.billing.service import count_platform_fee
            await count_platform_fee(db, payment.platform_fee)
        jobs.enqueue(db, "payments.succeeded", org_id=str(payment.organization_id), payment_id=str(payment.id))
    elif target in ("failed", "expired"):
        await _release(db, _reservation_of(payment))
        if sub is not None and sub.payment_status != "paid":
            sub.payment_status = target
    elif target == "pending" and sub is not None and sub.payment_status != "paid":
        sub.payment_status = "pending"
    if payment.purpose in ("subscription", "pass", "study") and target == "succeeded":
        jobs.enqueue(db, f"billing.{payment.purpose}_paid", org_id=str(payment.organization_id),
                     payment_id=str(payment.id))
    return True


async def _receipt_number(db: AsyncSession) -> str:
    seq = (await db.execute(text("select nextval('receipt_number_seq')"))).scalar_one()
    return f"AR-{clock.now().astimezone(clock.DOUALA).year}-{int(seq):06d}"


# ------------------------------------------------------------------ public charge flow


def public_view(p: Payment) -> dict[str, Any]:
    view: dict[str, Any] = {"id": p.id, "status": p.status, "amount": p.amount, "currency": p.currency,
                            "platform_fee": p.platform_fee, "fee_bearer": p.fee_bearer, "expires_at": p.expires_at,
                            "receipt_number": p.receipt_number, "failure_reason": p.failure_reason,
                            "submission_id": p.submission_id}
    if p.status == "succeeded":
        view["access_token"] = sign_compact({"p": str(p.id), "k": "receipt"})
    return view


async def start_payment(ctx: Any, *, org: Any, form: Any, submission_id: uuid.UUID, msisdn: str,
                        channel: str | None, idempotency_key: str, provider_code: str,
                        schema: dict[str, Any], purpose: str = "submission") -> dict[str, Any]:
    """Create the payment and commit, call the provider outside any transaction, then record its answer.

    `ctx.db` carries the tenant context; `ctx.checkpoint()` commits and reopens it on the same connection.
    """
    e164, operator = normalize_msisdn(msisdn, org.country)
    chosen = channel if channel in ("mtn", "orange") else operator
    key_hash = sha256_hex(f"{org.id}:{idempotency_key}")
    provider = get_provider(provider_code)
    from arha.modules.submissions.models import Submission

    db: AsyncSession = ctx.db
    # Transaction 1: validate, reserve, create.
    existing = (await db.execute(select(Payment).where(Payment.idempotency_key == key_hash))).scalar_one_or_none()
    if existing is not None:
        return public_view(existing)  # double click or network replay: same payment (F-PAY-04)
    sub = (await db.execute(select(Submission).where(Submission.id == submission_id).with_for_update())
           ).scalar_one_or_none()
    if sub is None or sub.form_id != form.id or sub.submitted_at is None:
        raise NotFound("submission_not_found")
    if sub.payment_status == "paid":
        raise AppError("payment_already_paid", 409)
    if sub.payment_status == "none" or not sub.amount_due:
        raise AppError("payment_not_required", 409)
    active = (await db.execute(select(Payment).where(
        Payment.submission_id == sub.id, Payment.status.in_(("created", "pending")),
        Payment.expires_at > clock.now()))).scalar_one_or_none()
    if active is not None:
        raise AppError("payment_in_progress", 409, extra={"payment_id": str(active.id)})
    computed = sub.computed or {}
    amount = int(computed.get("total_to_pay") or sub.amount_due)  # server computed, never from the browser
    if amount <= 0:
        raise AppError("payment_amount_invalid", 422)
    fee_bearer = ((schema.get("settings") or {}).get("payments") or {}).get("feeBearer", "org")
    account = await get_account(db, provider.code)
    connected = account.provider_account_id if account and account.status == "verified" else None
    if provider.code != "fake" and provider.supports_platform_fee and connected is None:
        raise AppError("payment_account_required", 422)
    reservation = await _reserve(db, form.id, _ticket_lines(sub, schema))
    payment = Payment(
        id=uuid7(), submission_id=sub.id, purpose=purpose, provider=provider.code, channel=chosen, amount=amount,
        currency=sub.currency or org.currency, platform_fee=int(computed.get("platform_fee", 0)),
        provider_fee=int(computed.get("estimated_provider_fee", 0)), fee_bearer=fee_bearer, status="created",
        idempotency_key=key_hash, payer_msisdn_hash=keyed_hash(e164),
        raw_events=[{"type": "reservation", "items": reservation}],
        expires_at=clock.now() + timedelta(minutes=get_plans().payment_expiry_minutes))
    db.add(payment)
    await db.flush()
    payment_id = payment.id
    request = ChargeRequest(
        idempotency_key=key_hash, amount=amount, currency=payment.currency, msisdn=e164,
        channel=chosen if chosen in ("mtn", "orange") else "auto",  # type: ignore[arg-type]
        connected_account_id=connected, platform_fee=payment.platform_fee,
        description=form.title[:100], reference=str(payment_id),
        callback_url=f"{get_settings().arha_api_url}/v1/webhooks/{provider.code}")
    await ctx.checkpoint()
    return await _charge_and_record(ctx, provider, request, payment_id)


async def _charge_and_record(ctx: Any, provider: Any, request: ChargeRequest, payment_id: uuid.UUID
                             ) -> dict[str, Any]:
    # Outside any transaction: the provider call.
    try:
        initiated = await provider.initiate_charge(request)
        provider_error = None
    except ProviderError as exc:
        initiated = None
        provider_error = exc.code

    # Transaction 2: record the outcome.
    db: AsyncSession = ctx.db
    payment = (await db.execute(select(Payment).where(Payment.id == payment_id).with_for_update())).scalar_one()
    if initiated is None:
        await apply_status(db, payment, "failed", source="initiate", failure_reason=provider_error)
    elif initiated.status == "failed":
        payment.provider_ref = initiated.provider_ref
        await apply_status(db, payment, "failed", source="initiate", failure_reason="declined")
    else:
        payment.provider_ref = initiated.provider_ref
        await apply_status(db, payment, "pending", source="initiate")
        payment.next_poll_at = clock.now() + timedelta(seconds=POLL_DELAYS[0])
        jobs.enqueue(db, "payments.poll", schedule_in=POLL_DELAYS[0], org_id=str(payment.organization_id),
                     payment_id=str(payment_id))
    view = public_view(payment)
    if provider_error:
        await ctx.checkpoint()  # keep the failed state, then report the outage
        raise AppError("payment_provider_unavailable", 503, extra={"payment": {"id": str(payment_id)}})
    return view


async def get_payment(db: AsyncSession, payment_id: uuid.UUID) -> Payment:
    p = await db.get(Payment, payment_id)
    if p is None:
        raise NotFound("payment_not_found")
    return p


async def payments_for_submission(db: AsyncSession, submission_id: uuid.UUID) -> list[dict[str, Any]]:
    rows = (await db.execute(select(Payment).where(Payment.submission_id == submission_id)
                             .order_by(Payment.created_at.desc()))).scalars()
    return [{"id": p.id, "status": p.status, "amount": p.amount, "currency": p.currency, "provider": p.provider,
             "provider_ref": p.provider_ref, "channel": p.channel, "platform_fee": p.platform_fee,
             "receipt_number": p.receipt_number, "created_at": p.created_at} for p in rows]


# ------------------------------------------------------------------ confirmation: webhook, polling, expiry


async def confirm_with_provider(db: AsyncSession, payment: Payment, *, source: str) -> None:
    """Counter-verification (S-19): the provider status is always re-read before any transition."""
    if payment.status in TERMINAL - {"expired"} or not payment.provider_ref:
        return
    provider = get_provider(payment.provider)
    try:
        status = await provider.get_charge(payment.provider_ref)
    except ProviderError:
        return
    if status.status == "succeeded":
        if (status.amount is not None and status.amount != payment.amount) or (
                status.currency and status.currency != payment.currency):
            db.add(ReconciliationAlert(id=uuid7(), organization_id=payment.organization_id, provider=payment.provider,
                                       provider_ref=payment.provider_ref, payment_id=payment.id,
                                       kind="amount_mismatch",
                                       details={"expected": payment.amount, "received": status.amount}))
            log.error("payment_amount_mismatch", payment_id=str(payment.id))
            return
        await apply_status(db, payment, "succeeded", source=source)
    elif status.status in ("failed", "expired") and payment.status != "expired":
        await apply_status(db, payment, status.status, source=source, failure_reason=status.failure_reason)


async def handle_webhook(provider_code: str, headers: dict[str, str], body: bytes) -> None:
    provider = get_provider(provider_code)
    event = provider.verify_webhook(headers, body)  # raises SignatureError
    org_id = None
    from arha.db.session import platform_tx

    async with platform_tx() as pdb:  # narrow lookup of the tenant, no row data read
        if event.provider_ref:
            org_id = (await pdb.execute(text("select resolve_org('payment_ref', :k)"),
                                        {"k": event.provider_ref})).scalar()
        if org_id is None and event.reference:
            org_id = (await pdb.execute(text("select resolve_org('payment_reference', :k)"),
                                        {"k": event.reference})).scalar()
    if org_id is None:
        log.warning("webhook_unknown_payment", provider=provider_code)
        return
    async with app_tx(org_id=org_id) as db:
        stmt = select(Payment).with_for_update()
        if event.provider_ref:
            stmt = stmt.where(Payment.provider_ref == event.provider_ref)
        else:
            stmt = stmt.where(Payment.id == uuid.UUID(str(event.reference)))
        payment = (await db.execute(stmt)).scalar_one_or_none()
        if payment is None:
            return
        payment.raw_events = [*(payment.raw_events or []), {"type": "webhook", "event": event.raw.get("event"),
                                                            "status": event.status, "at": clock.now().isoformat()}]
        await confirm_with_provider(db, payment, source="webhook")


async def poll(org_id: uuid.UUID, payment_id: uuid.UUID) -> None:
    async with app_tx(org_id=org_id) as db:
        payment = (await db.execute(select(Payment).where(Payment.id == payment_id).with_for_update())
                   ).scalar_one_or_none()
        if payment is None or payment.status in TERMINAL:
            return
        await confirm_with_provider(db, payment, source="poll")
        if payment.status in TERMINAL:
            return
        payment.poll_attempts += 1
        if clock.now() >= payment.expires_at:
            await apply_status(db, payment, "expired", source="poll")
            return
        delay = POLL_DELAYS[min(payment.poll_attempts, len(POLL_DELAYS) - 1)]
        remaining = int((payment.expires_at - clock.now()).total_seconds())
        delay = max(30, min(delay, remaining + 1))
        payment.next_poll_at = clock.now() + timedelta(seconds=delay)
        jobs.enqueue(db, "payments.poll", schedule_in=delay, org_id=str(org_id), payment_id=str(payment_id))


# ------------------------------------------------------------------ reconciliation (F-PAY-09)


async def reconcile(window_hours: int = 48) -> int:
    """Compare provider transactions with Arha payments over a sliding window. Returns alerts created."""
    from arha.db.session import platform_tx

    until = clock.now()
    since = until - timedelta(hours=window_hours)
    created = 0
    for provider_code in _active_providers():
        try:
            txns = await get_provider(provider_code).list_transactions(since, until)
        except ProviderError:
            log.error("reconciliation_provider_unavailable", provider=provider_code)
            continue
        async with platform_tx() as db:
            ours = {p.provider_ref: p for p in (await db.execute(select(Payment).where(
                Payment.provider == provider_code, Payment.created_at >= since - timedelta(hours=1),
                Payment.provider_ref.is_not(None)))).scalars()}
            seen: set[str] = set()
            for tx in txns:
                seen.add(tx.provider_ref)
                p = ours.get(tx.provider_ref)
                kind: str | None = None
                details: dict[str, Any] = {}
                org = None
                if p is None:
                    kind, details = "unknown_transaction", {"amount": tx.amount, "status": tx.status}
                else:
                    org = p.organization_id
                    if tx.status == "succeeded" and tx.amount != p.amount:
                        kind, details = "amount_mismatch", {"expected": p.amount, "received": tx.amount}
                    elif (tx.status == "succeeded") != (p.status == "succeeded") and tx.status != "pending":
                        kind, details = "status_mismatch", {"ours": p.status, "provider": tx.status}
                if kind and not await _alert_exists(db, provider_code, tx.provider_ref, kind):
                    db.add(ReconciliationAlert(id=uuid7(), organization_id=org, provider=provider_code,
                                               provider_ref=tx.provider_ref, payment_id=p.id if p else None,
                                               kind=kind, details=details))
                    created += 1
            for ref, p in ours.items():
                fresh = bool(ref) and p.status == "succeeded" and ref not in seen and p.created_at >= since
                if fresh and ref and not await _alert_exists(
                        db, provider_code, ref, "missing_at_provider"):
                    db.add(ReconciliationAlert(id=uuid7(), organization_id=p.organization_id, provider=provider_code,
                                               provider_ref=ref, payment_id=p.id, kind="missing_at_provider",
                                               details={"amount": p.amount}))
                    created += 1
            await trust.audit(db, "platform.reconciliation", org_id=None, actor_id=None,
                              metadata={"provider": provider_code, "alerts": created, "transactions": len(txns)})
    return created


def _active_providers() -> list[str]:
    override = get_settings().payment_provider_override
    if override:
        return [override]
    codes: list[str] = []
    for country in get_countries().countries.values():
        if country.active:
            codes.extend(c for c in country.providers if c not in codes)
    return codes


async def _alert_exists(db: AsyncSession, provider: str, ref: str, kind: str) -> bool:
    return (await db.execute(select(func.count()).select_from(ReconciliationAlert).where(
        ReconciliationAlert.provider == provider, ReconciliationAlert.provider_ref == ref,
        ReconciliationAlert.kind == kind, ReconciliationAlert.resolved_at.is_(None)))).scalar_one() > 0


# ------------------------------------------------------------------ dashboard (F-ANA-03)


async def summary(db: AsyncSession, form_id: uuid.UUID | None = None) -> dict[str, Any]:
    base = select(Payment).where(Payment.purpose == "submission")
    if form_id:
        from arha.modules.submissions.models import Submission
        base = base.join(Submission, Submission.id == Payment.submission_id).where(Submission.form_id == form_id)
    sub = base.subquery()
    rows = (await db.execute(select(sub.c.status, func.count(), func.coalesce(func.sum(sub.c.amount), 0),
                                    func.coalesce(func.sum(sub.c.platform_fee), 0)).group_by(sub.c.status))).all()
    by_status = {r[0]: {"count": int(r[1]), "amount": int(r[2]), "platform_fee": int(r[3])} for r in rows}
    ok = by_status.get("succeeded", {"count": 0, "amount": 0, "platform_fee": 0})
    attempts = sum(v["count"] for k, v in by_status.items() if k in ("succeeded", "failed", "expired"))
    return {"collected": ok["amount"], "platform_fees": ok["platform_fee"], "succeeded": ok["count"],
            "failed": by_status.get("failed", {}).get("count", 0),
            "expired": by_status.get("expired", {}).get("count", 0),
            "pending": by_status.get("pending", {}).get("count", 0) + by_status.get("created", {}).get("count", 0),
            "success_rate": round(ok["count"] / attempts, 4) if attempts else None, "by_status": by_status}


async def list_payments(db: AsyncSession, *, status: str | None, limit: int, offset: int) -> list[Payment]:
    stmt = select(Payment).order_by(Payment.created_at.desc()).limit(limit).offset(offset)
    if status:
        stmt = stmt.where(Payment.status == status)
    return list((await db.execute(stmt)).scalars())


# ------------------------------------------------------------------ ticket scanning (F-PAY-08)


async def scan(db: AsyncSession, token: str, user_id: uuid.UUID) -> dict[str, Any]:
    from arha.core.crypto import verify_compact

    try:
        payload = verify_compact(token)
    except Exception as exc:
        raise AppError("ticket_invalid", 422) from exc
    ticket = (await db.execute(select(Ticket).where(Ticket.token_hash == sha256_hex(token)).with_for_update())
              ).scalar_one_or_none()
    if ticket is None or str(ticket.id) != payload.get("t"):
        raise AppError("ticket_invalid", 422)
    cat = await db.get(TicketCategory, ticket.category_id)
    result = {"ticket_id": ticket.id, "serial": ticket.serial, "category": cat.name if cat else None,
              "already_scanned": ticket.scanned_at is not None, "scanned_at": ticket.scanned_at}
    if ticket.scanned_at is None:
        ticket.scanned_at = clock.now()
        ticket.scanned_by = user_id
        result["scanned_at"] = ticket.scanned_at
    return result


async def offline_bundle(db: AsyncSession, form_id: uuid.UUID) -> dict[str, Any]:
    from arha.core.crypto import public_key_b64

    rows = (await db.execute(select(Ticket, TicketCategory.name).join(
        TicketCategory, TicketCategory.id == Ticket.category_id).where(Ticket.form_id == form_id))).all()
    return {"public_key": public_key_b64(), "generated_at": clock.now(),
            "tickets": [{"id": t.id, "hash": t.token_hash, "serial": t.serial, "category": name,
                         "scanned_at": t.scanned_at} for t, name in rows]}


async def sync_scans(db: AsyncSession, scans: list[dict[str, Any]], user_id: uuid.UUID) -> dict[str, Any]:
    """Offline scans uploaded on reconnection. Duplicates (scanned elsewhere first) are reported."""
    duplicates: list[str] = []
    accepted = 0
    for item in scans[:5000]:
        ticket = (await db.execute(select(Ticket).where(Ticket.token_hash == str(item.get("hash")))
                                   .with_for_update())).scalar_one_or_none()
        if ticket is None:
            continue
        if ticket.scanned_at is not None:
            duplicates.append(ticket.token_hash)
            continue
        ticket.scanned_at = clock.now()
        ticket.scanned_by = user_id
        accepted += 1
    return {"accepted": accepted, "duplicates": duplicates}


# One constant statement per purpose: no SQL is assembled from a variable.
_LINKS = {
    "subscription": text("update subscriptions set payment_id = :p where id = :s"),
    "pass": text("update student_passes set payment_id = :p where id = :s"),
    "study": text("update study_orders set payment_id = :p where id = :s"),
}


async def start_platform_payment(ctx: Any, *, org: Any, amount: int, msisdn: str, idempotency_key: str,
                                 description: str, purpose: str, link_id: uuid.UUID
                                 ) -> tuple[uuid.UUID, dict[str, Any]]:
    """Payment of an Arha sale (subscription, Pass Mémoire, Arha Services or Arha Études order, section 9.0).

    This is Arha's own revenue, collected on Arha's merchant account: never a connected account.
    """
    if purpose not in _LINKS:
        raise ValueError(purpose)
    e164, operator = normalize_msisdn(msisdn, org.country)
    key_hash = sha256_hex(f"{org.id}:{purpose}:{idempotency_key}")
    provider = get_provider(resolve_code(None))
    db: AsyncSession = ctx.db
    existing = (await db.execute(select(Payment).where(Payment.idempotency_key == key_hash))).scalar_one_or_none()
    if existing is not None:
        return existing.id, public_view(existing)
    payment = Payment(id=uuid7(), purpose=purpose, provider=provider.code, channel=operator,
                      amount=amount, currency=org.currency, platform_fee=0, fee_bearer="org", status="created",
                      idempotency_key=key_hash, payer_msisdn_hash=keyed_hash(e164),
                      expires_at=clock.now() + timedelta(minutes=get_plans().payment_expiry_minutes))
    db.add(payment)
    await db.flush()
    payment_id = payment.id
    # Linked before the provider call so an early webhook always finds what was bought.
    await db.execute(_LINKS[purpose],
                     {"p": payment_id, "s": link_id})
    request = ChargeRequest(idempotency_key=key_hash, amount=amount, currency=org.currency, msisdn=e164,
                            channel=operator if operator in ("mtn", "orange") else "auto",  # type: ignore[arg-type]
                            connected_account_id=None, platform_fee=0, description=description[:100],
                            reference=str(payment_id),
                            callback_url=f"{get_settings().arha_api_url}/v1/webhooks/{provider.code}")
    await ctx.checkpoint()
    return payment_id, await _charge_and_record(ctx, provider, request, payment_id)
