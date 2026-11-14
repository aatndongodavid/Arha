from __future__ import annotations

import uuid

from sqlalchemy import select

from arha.core.jobs import job
from arha.core.messages import t
from arha.core.money import fmt
from arha.db.session import app_tx
from arha.modules.messaging import service as mail
from arha.modules.payments import service
from arha.workers.app import worker_app


@job("payments.poll", retry=5)
async def poll_payment(org_id: str, payment_id: str) -> None:
    """Active verification when no webhook arrived (F-PAY-03): exponential backoff up to expiry."""
    await service.poll(uuid.UUID(org_id), uuid.UUID(payment_id))


@job("payments.succeeded")
async def payment_succeeded(org_id: str, payment_id: str) -> None:
    """Receipt e-mail with PDF and tickets, then the usual completion side effects."""
    from arha.modules.forms.models import Form, FormVersion
    from arha.modules.orgs.service import get_org
    from arha.modules.payments.documents import receipt_pdf, tickets_pdf
    from arha.modules.payments.models import Payment, Ticket, TicketCategory
    from arha.modules.submissions.models import Submission

    oid = uuid.UUID(org_id)
    async with app_tx(org_id=oid) as db:
        payment = await db.get(Payment, uuid.UUID(payment_id))
        if payment is None or payment.purpose != "submission" or payment.submission_id is None:
            return
        sub = await db.get(Submission, payment.submission_id)
        assert sub
        form = await db.get(Form, sub.form_id)
        version = await db.get(FormVersion, sub.form_version_id)
        org = await get_org(db, oid)
        assert form and version
        locale = sub.locale
        settings = version.schema.get("settings") or {}
        field = settings.get("respondentEmailField")
        to = (sub.answers or {}).get(field) if field else None
        rows = (await db.execute(select(Ticket, TicketCategory.name).join(
            TicketCategory, TicketCategory.id == Ticket.category_id).where(Ticket.submission_id == sub.id)
            .order_by(Ticket.serial))).all()
        tickets = [{"token": tk.signed_token, "serial": tk.serial, "category": name} for tk, name in rows]
        if to:
            attachments = [(f"{payment.receipt_number}.pdf", receipt_pdf(
                locale=locale, org_name=org.name, form_title=form.title, payment=payment,
                channel_label=(payment.channel or "").upper()), "application/pdf")]
            if tickets:
                attachments.append(("billets.pdf" if locale == "fr" else "tickets.pdf", tickets_pdf(
                    locale=locale, org_name=org.name, form_title=form.title, tickets=tickets), "application/pdf"))
            subject, body = mail.render(
                "receipt", locale, number=payment.receipt_number, form=form.title, org=org.name,
                amount=fmt(payment.amount, payment.currency, locale), provider_ref=payment.provider_ref or "",
                tickets=("\n" + t("ticket.title", locale) + " : " + str(len(tickets))) if tickets else "")
            await mail.send(mail.Mail(to=str(to), subject=subject, text=body, template="receipt",
                                      attachments=attachments), db=db, org_id=oid)
    from arha.modules.submissions.tasks import submission_completed
    await submission_completed(org_id, str(payment.submission_id))


@job("payments.reconcile")
async def reconcile_job() -> None:
    await service.reconcile()


# Daily at 03:00 Africa/Douala, which is 02:00 UTC (master prompt 9.7).
@worker_app.periodic(cron="0 2 * * *")
@worker_app.task(name="payments.reconcile_daily", pass_context=False)
async def reconcile_daily(timestamp: int) -> None:
    await service.reconcile()


@worker_app.periodic(cron="*/5 * * * *")
@worker_app.task(name="payments.sweep", pass_context=False)
async def sweep(timestamp: int) -> None:
    """Safety net: expire or re-poll payments whose scheduled poll was lost."""
    from sqlalchemy import text

    from arha.core import clock
    from arha.db.session import platform_tx

    async with platform_tx() as db:
        rows = (await db.execute(text(
            "select id, organization_id from payments where status in ('created','pending') "
            "and coalesce(next_poll_at, created_at) < :t"), {"t": clock.now()})).all()
    for pid, oid in rows:
        await service.poll(oid, pid)
