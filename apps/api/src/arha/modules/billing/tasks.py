from __future__ import annotations

import uuid
from datetime import timedelta

from sqlalchemy import select, text

from arha.core import clock
from arha.core.jobs import job
from arha.core.money import fmt
from arha.core.plans import get_plans
from arha.db.session import app_tx, platform_tx
from arha.modules.messaging import service as mail
from arha.settings import get_settings
from arha.workers.app import worker_app


@job("billing.subscription_paid")
async def subscription_paid(org_id: str, payment_id: str) -> None:
    from arha.modules.billing.documents import render_invoice
    from arha.modules.billing.service import activate
    from arha.modules.orgs.service import get_org, owners_emails
    from arha.modules.payments.models import Payment
    from arha.modules.trust import service as trust

    oid = uuid.UUID(org_id)
    async with app_tx(org_id=oid) as db:
        payment = await db.get(Payment, uuid.UUID(payment_id))
        org = await get_org(db, oid)
        if payment is None:
            return
        invoice = await activate(db, org, payment)
        if invoice is None:
            return
        await trust.audit(db, "billing.plan_activated", org_id=oid, actor_id=None,
                          metadata={"plan": org.plan_code, "invoice": invoice.number})
        for email, locale in await owners_emails(db):
            subject, body = mail.render("invoice", locale, number=invoice.number,
                                        amount=fmt(invoice.amount, invoice.currency, locale))
            await mail.send(mail.Mail(to=email, subject=subject, text=body, template="invoice", attachments=[
                (f"{invoice.number}.pdf", render_invoice(invoice, org, locale), "application/pdf")]), db=db, org_id=oid)


@job("billing.quota_alert")
async def quota_alert(org_id: str, used: int, limit: int) -> None:
    from arha.modules.orgs.service import get_org, owners_emails

    oid = uuid.UUID(org_id)
    async with app_tx(org_id=oid) as db:
        org = await get_org(db, oid)
        link = f"{get_settings().arha_app_url}/orgs/{org_id}/billing"
        for email, locale in await owners_emails(db):
            subject, body = mail.render("quota_alert", locale, pct=min(100, used * 100 // max(1, limit)), org=org.name,
                                        used=used, limit=limit, link=link)
            await mail.send(mail.Mail(to=email, subject=subject, text=body, template="quota_alert"), db=db, org_id=oid)


async def renewal_cycle() -> dict[str, int]:
    """F-FAC-02: reminder 7 days before the end; back to Discovery 7 days after an unpaid end. No data deleted."""
    cfg = get_plans().renewal
    now = clock.now()
    reminded = downgraded = 0
    async with platform_tx() as db:
        due = (await db.execute(text(
            "select id, organization_id from subscriptions where status = 'active' and reminded_at is null "
            "and period_end <= :limit"), {"limit": now + timedelta(days=cfg.remind_days_before)})).all()
        lapsed = (await db.execute(text(
            "select id, organization_id from subscriptions where status in ('active','past_due') and period_end <= :t"),
            {"t": now - timedelta(days=cfg.downgrade_after_days_unpaid)})).all()
    from arha.modules.billing.models import Subscription
    from arha.modules.orgs.service import get_org, owners_emails
    from arha.modules.trust import service as trust

    for sid, oid in due:
        async with app_tx(org_id=oid) as db:
            sub = await db.get(Subscription, sid)
            org = await get_org(db, oid)
            if sub is None or sub.period_end is None:
                continue
            sub.reminded_at = now
            for email, locale in await owners_emails(db):
                subject, body = mail.render("renewal_reminder", locale, plan=sub.plan_code.capitalize(), org=org.name,
                                            date=f"{sub.period_end:%d/%m/%Y}",
                                            link=f"{get_settings().arha_app_url}/orgs/{oid}/billing")
                await mail.send(mail.Mail(to=email, subject=subject, text=body, template="renewal_reminder"),
                                db=db, org_id=oid)
            reminded += 1
    for sid, oid in lapsed:
        async with app_tx(org_id=oid) as db:
            sub = await db.get(Subscription, sid)
            org = await get_org(db, oid)
            if sub is None:
                continue
            sub.status = "expired"
            newer = (await db.execute(select(Subscription).where(Subscription.status == "active",
                                                                 Subscription.id != sid))).first()
            if newer is None:
                org.plan_code = "discovery"
                await trust.audit(db, "billing.downgraded", org_id=oid, actor_id=None, metadata={"from": sub.plan_code})
                downgraded += 1
    return {"reminded": reminded, "downgraded": downgraded}


@worker_app.periodic(cron="15 6 * * *")
@worker_app.task(name="billing.renewal_daily", pass_context=False)
async def renewal_daily(timestamp: int) -> None:
    await renewal_cycle()
