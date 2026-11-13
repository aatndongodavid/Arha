"""Plans, subscriptions, invoices and usage quotas (F-FAC-01..05)."""

from __future__ import annotations

import uuid
from datetime import datetime, timedelta
from typing import Any

from sqlalchemy import select, text
from sqlalchemy.ext.asyncio import AsyncSession

from arha.core import clock, jobs
from arha.core.errors import AppError
from arha.core.plans import get_plans
from arha.modules.billing.models import Invoice, Subscription, UsageCounter


def period_of(at: datetime | None = None) -> str:
    return (at or clock.now()).astimezone(clock.DOUALA).strftime("%Y-%m")


def _period_start(period: str) -> datetime:
    y, m = map(int, period.split("-"))
    return datetime(y, m, 1, tzinfo=clock.DOUALA)


async def usage(db: AsyncSession, metric: str = "responses", period: str | None = None) -> int:
    row = await db.get(UsageCounter, (await _org_id(db), metric, period or period_of()))
    return row.value if row else 0


async def _org_id(db: AsyncSession) -> uuid.UUID:
    return (await db.execute(text("select app_org()"))).scalar_one()  # type: ignore[no-any-return]


async def admit_response(db: AsyncSession, org: Any) -> bool:
    """Count one completed response. Returns True when the response is accepted over quota (grace period).

    At 80 % an alert is sent once per period. At 100 % responses stay accepted for `grace_hours`,
    then they are refused with a clear message (F-FAC-03).
    """
    plans = get_plans()
    limit = plans.limit(org.plan_code, "responses_per_month")
    period = period_of()
    if org.quota_exceeded_at is not None and org.quota_exceeded_at < _period_start(period):
        org.quota_exceeded_at = None  # new period
    grace = timedelta(hours=plans.quota_policy.grace_hours)
    if limit is not None and org.quota_exceeded_at is not None and clock.now() - org.quota_exceeded_at > grace:
        raise AppError("quota_exceeded", 429)
    value = (await db.execute(text(
        "insert into usage_counters (organization_id, metric, period, value) values (app_org(), 'responses', :p, 1) "
        "on conflict (organization_id, metric, period) do update set value = usage_counters.value + 1 "
        "returning value"), {"p": period})).scalar_one()
    if limit is None:
        return False
    if value * 100 >= limit * plans.quota_policy.alert_at_pct:
        alerted = (await db.execute(text(
            "update usage_counters set alerted_at = now() where organization_id = app_org() and metric = 'responses' "
            "and period = :p and alerted_at is null returning 1"), {"p": period})).first()
        if alerted:
            jobs.enqueue(db, "billing.quota_alert", org_id=str(org.id), used=int(value), limit=int(limit))
    if value > limit:
        if org.quota_exceeded_at is None:
            org.quota_exceeded_at = clock.now()
        return True
    return False


async def count_platform_fee(db: AsyncSession, amount: int) -> None:
    """Fallback provider without platform fee split: the fee is invoiced monthly (master prompt 9.2)."""
    await db.execute(text(
        "insert into usage_counters (organization_id, metric, period, value) values (app_org(), 'platform_fee_due', "
        ":p, :v) on conflict (organization_id, metric, period) do update set value = usage_counters.value + :v"),
        {"p": period_of(), "v": amount})


async def active_subscription(db: AsyncSession) -> Subscription | None:
    stmt = select(Subscription).where(Subscription.status.in_(("active", "past_due"))).order_by(
        Subscription.period_end.desc().nullslast()).limit(1)
    return (await db.execute(stmt)).scalar_one_or_none()


async def list_invoices(db: AsyncSession) -> list[Invoice]:
    return list((await db.execute(select(Invoice).order_by(Invoice.issued_at.desc()))).scalars())


def plan_price(org: Any, plan_code: str, period: str, *, pioneer_available: bool) -> tuple[int, int, bool]:
    """Return (amount, discount_bps, pioneer). Discounts are not cumulative (section 11)."""
    plans = get_plans()
    plan = plans.plans.get(plan_code)
    if plan is None:
        raise AppError("plan_unknown", 404)
    if plan.custom or not plan.price_monthly:
        raise AppError("plan_not_purchasable", 422)
    base = plan.price_monthly if period == "monthly" else plans.yearly_price(plan_code)
    discounts: list[tuple[int, bool]] = []
    if pioneer_available:
        discounts.append((plans.pioneer.discount_bps, True))
    np = plans.nonprofit_discount
    if org.is_nonprofit and org.verified_at is not None and plan_code == np.plan:
        discounts.append((np.discount_bps, False))
    bps, pioneer = max(discounts) if discounts else (0, False)
    amount = base - (base * bps // 10_000)
    return amount, bps, pioneer


async def pioneer_seats_left(db: AsyncSession) -> int:
    """Counted platform wide with a SECURITY DEFINER-free platform query by the caller."""
    from arha.db.session import platform_tx

    async with platform_tx() as pdb:
        used = (await pdb.execute(text(
            "select count(distinct organization_id) from subscriptions where pioneer and status in "
            "('active','past_due','expired','canceled')"))).scalar_one()
    return max(0, get_plans().pioneer.seats - int(used))


async def has_used_pioneer(db: AsyncSession) -> bool:
    return (await db.execute(select(Subscription.id).where(Subscription.pioneer.is_(True)).limit(1))).first() is not None


async def create_subscription(db: AsyncSession, org: Any, plan_code: str, period: str) -> Subscription:
    pioneer_ok = not await has_used_pioneer(db) and await pioneer_seats_left(db) > 0
    amount, bps, pioneer = plan_price(org, plan_code, period, pioneer_available=pioneer_ok)
    sub = Subscription(plan_code=plan_code, billing_period=period, amount=amount, currency=org.currency,
                       status="pending_payment", pioneer=pioneer, discount_bps=bps)
    db.add(sub)
    await db.flush()
    return sub


async def activate(db: AsyncSession, org: Any, payment: Any) -> Invoice | None:
    """F-FAC-01: the plan is active as soon as the payment is confirmed. F-FAC-04: numbered invoice."""
    sub = (await db.execute(select(Subscription).where(Subscription.payment_id == payment.id).with_for_update())
           ).scalar_one_or_none()
    if sub is None or sub.status == "active":
        return None
    current = await active_subscription(db)
    start = current.period_end if current and current.period_end and current.period_end > clock.now() else clock.now()
    months = 1 if sub.billing_period == "monthly" else 12
    sub.period_start = start
    sub.period_end = _add_months(start, months)
    sub.status = "active"
    if current and current.id != sub.id:
        current.status = "canceled"
    org.plan_code = sub.plan_code
    org.quota_exceeded_at = None
    seq = (await db.execute(text("select nextval('invoice_number_seq')"))).scalar_one()
    number = f"ARHA-{clock.now().astimezone(clock.DOUALA).year}-{int(seq):05d}"
    invoice = Invoice(number=number, amount=payment.amount, currency=payment.currency, payment_id=payment.id,
                      lines=[{"plan": sub.plan_code, "period": sub.billing_period, "amount": sub.amount,
                              "discount_bps": sub.discount_bps, "pioneer": sub.pioneer,
                              "from": sub.period_start.isoformat(), "to": sub.period_end.isoformat()}])
    db.add(invoice)
    await db.flush()
    return invoice


def _add_months(at: datetime, months: int) -> datetime:
    import calendar

    month = at.month - 1 + months
    year = at.year + month // 12
    month = month % 12 + 1
    day = min(at.day, calendar.monthrange(year, month)[1])
    return at.replace(year=year, month=month, day=day)
