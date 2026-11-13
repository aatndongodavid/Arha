from __future__ import annotations

import uuid
from typing import Any, Literal

from fastapi import APIRouter, Depends, Header, Query, Request, Response
from pydantic import BaseModel, ConfigDict, Field
from sqlalchemy import select

from arha.core import idempotency, ratelimit
from arha.core.context import Ctx, public_route, require_permission
from arha.core.crypto import verify_compact
from arha.core.errors import AppError, NotFound
from arha.modules.payments import service
from arha.modules.payments.adapters.base import SignatureError
from arha.modules.payments.adapters.registry import resolve_code
from arha.modules.payments.models import Payment, Ticket, TicketCategory
from arha.modules.trust import service as trust

router = APIRouter(tags=["payments"])


class PayIn(BaseModel):
    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)
    msisdn: str = Field(min_length=8, max_length=20)
    channel: Literal["mtn", "orange", "auto"] = "auto"


class ConnectIn(BaseModel):
    model_config = ConfigDict(extra="forbid")
    provider: Literal["notchpay", "campay", "fake"] = "notchpay"


class ScanIn(BaseModel):
    model_config = ConfigDict(extra="forbid")
    token: str = Field(min_length=20, max_length=1000)


class SyncIn(BaseModel):
    model_config = ConfigDict(extra="forbid")
    scans: list[dict[str, Any]] = Field(max_length=5000)


# ------------------------------------------------------------------ public


@router.post("/v1/public/forms/{code}/submissions/{submission_id}/payments", status_code=201)
async def pay(code: str, submission_id: uuid.UUID, body: PayIn,
              idempotency_key: str | None = Header(default=None, alias="Idempotency-Key"),
              ctx: Ctx = Depends(public_route)) -> dict[str, Any]:
    """F-PAY-02: the respondent enters a number and approves on the phone. No PIN ever (rule 3)."""
    key = idempotency.require_key(idempotency_key)
    await ratelimit.limit("submission", ctx.ip_hash or "", f"{code}:pay")
    from arha.modules.submissions.public_router import _provider_for, resolve

    form, org, version = await resolve(ctx, code)
    if version is None:
        raise AppError("form_unavailable", 410)
    from arha.modules.forms.models import FormVersion
    from arha.modules.submissions.models import Submission

    sub = await ctx.db.get(Submission, submission_id)
    if sub is None or sub.form_id != form.id:
        raise NotFound("submission_not_found")
    used = await ctx.db.get(FormVersion, sub.form_version_id)
    schema = used.schema if used else version.schema
    return await service.start_payment(org_id=org.id, org=org, form=form, submission_id=submission_id,
                                       msisdn=body.msisdn, channel=body.channel, idempotency_key=key,
                                       provider_code=_provider_for(schema), schema=schema)


@router.get("/v1/public/payments/{payment_id}")
async def payment_status(payment_id: uuid.UUID, ctx: Ctx = Depends(public_route)) -> dict[str, Any]:
    """Polled every 3 seconds by the form while waiting (master prompt 9.4 step 7)."""
    await ratelimit.limit("payment_status", ctx.ip_hash or "")
    from sqlalchemy import text

    from arha.db.session import set_org

    org_id = (await ctx.db.execute(text("select resolve_org('payment_id', :k)"), {"k": str(payment_id)})).scalar()
    if org_id is None:
        raise NotFound("payment_not_found")
    await set_org(ctx.db, org_id)
    return service.public_view(await service.get_payment(ctx.db, payment_id))


async def _payment_from_token(ctx: Ctx, payment_id: uuid.UUID, token: str) -> Payment:
    try:
        claims = verify_compact(token)
    except Exception as exc:  # noqa: BLE001
        raise NotFound("payment_not_found") from exc
    if claims.get("p") != str(payment_id) or claims.get("k") != "receipt":
        raise NotFound("payment_not_found")
    from sqlalchemy import text

    from arha.db.session import set_org

    org_id = (await ctx.db.execute(text("select resolve_org('payment_id', :k)"), {"k": str(payment_id)})).scalar()
    if org_id is None:
        raise NotFound("payment_not_found")
    await set_org(ctx.db, org_id)
    payment = await service.get_payment(ctx.db, payment_id)
    if payment.status != "succeeded":
        raise NotFound("payment_not_found")
    return payment


@router.get("/v1/public/payments/{payment_id}/receipt.pdf")
async def receipt(payment_id: uuid.UUID, t: str = Query(max_length=600), lang: str = "fr",
                  ctx: Ctx = Depends(public_route)) -> Response:
    from arha.modules.forms.models import Form
    from arha.modules.orgs.service import get_org
    from arha.modules.payments.documents import receipt_pdf
    from arha.modules.submissions.models import Submission

    payment = await _payment_from_token(ctx, payment_id, t)
    sub = await ctx.db.get(Submission, payment.submission_id) if payment.submission_id else None
    form = await ctx.db.get(Form, sub.form_id) if sub else None
    org = await get_org(ctx.db, payment.organization_id)
    pdf = receipt_pdf(locale="en" if lang == "en" else "fr", org_name=org.name, form_title=form.title if form else "",
                      payment=payment, channel_label=(payment.channel or "").upper())
    return Response(pdf, media_type="application/pdf", headers={
        "Content-Disposition": f'attachment; filename="{payment.receipt_number}.pdf"', "Cache-Control": "no-store"})


@router.get("/v1/public/payments/{payment_id}/tickets")
async def tickets(payment_id: uuid.UUID, t: str = Query(max_length=600),
                  ctx: Ctx = Depends(public_route)) -> list[dict[str, Any]]:
    """Tickets shown on the ending page with an SVG QR code (F-PAY-07)."""
    from arha.modules.payments.documents import qr_svg

    payment = await _payment_from_token(ctx, payment_id, t)
    rows = (await ctx.db.execute(select(Ticket, TicketCategory.name).join(
        TicketCategory, TicketCategory.id == Ticket.category_id).where(Ticket.submission_id == payment.submission_id)
        .order_by(Ticket.serial))).all()
    return [{"serial": tk.serial, "category": name, "token": tk.signed_token, "qr_svg": qr_svg(tk.signed_token)}
            for tk, name in rows]


@router.post("/v1/webhooks/{provider}", status_code=200)
async def webhook(provider: str, request: Request, ctx: Ctx = Depends(public_route)) -> dict[str, str]:
    """F-PAY-03: signature checked, then status counter-verified with get_charge before any transition."""
    if provider not in ("notchpay", "campay", "fake"):
        raise NotFound()
    body = await request.body()
    if len(body) > 64 * 1024:
        raise AppError("validation_failed", 413)
    try:
        await service.handle_webhook(resolve_code(provider), dict(request.headers), body)
    except SignatureError as exc:
        raise AppError("webhook_signature_invalid", 401) from exc
    return {"status": "ok"}


# ------------------------------------------------------------------ organisation


@router.get("/v1/orgs/{org_id}/payment-accounts")
async def accounts(ctx: Ctx = Depends(require_permission("payments:read"))) -> list[dict[str, Any]]:
    from arha.modules.payments.models import PaymentAccount

    rows = (await ctx.db.execute(select(PaymentAccount))).scalars()
    return [{"id": a.id, "provider": a.provider, "status": a.status, "onboarding_url": a.onboarding_url,
             "updated_at": a.updated_at} for a in rows]


@router.post("/v1/orgs/{org_id}/payment-accounts", status_code=201)
async def connect(body: ConnectIn, ctx: Ctx = Depends(require_permission("payments:manage"))) -> dict[str, Any]:
    """F-PAY-01: connection follows the aggregator's Sync flow; status pending, verified or suspended."""
    assert ctx.user
    account = await service.connect_account(ctx.db, ctx.org, body.provider, ctx.user.email)
    await trust.audit(ctx.db, "payments.account_connected", org_id=ctx.org_id, actor_id=ctx.user_id,
                      metadata={"provider": account.provider, "status": account.status})
    return {"id": account.id, "provider": account.provider, "status": account.status,
            "onboarding_url": account.onboarding_url}


@router.get("/v1/orgs/{org_id}/payments")
async def list_payments(status: str | None = Query(default=None, max_length=20),
                        limit: int = Query(default=50, ge=1, le=200), offset: int = Query(default=0, ge=0),
                        ctx: Ctx = Depends(require_permission("payments:read"))) -> list[dict[str, Any]]:
    rows = await service.list_payments(ctx.db, status=status, limit=limit, offset=offset)
    return [{"id": p.id, "submission_id": p.submission_id, "status": p.status, "amount": p.amount,
             "currency": p.currency, "platform_fee": p.platform_fee, "provider": p.provider, "channel": p.channel,
             "provider_ref": p.provider_ref, "receipt_number": p.receipt_number, "failure_reason": p.failure_reason,
             "created_at": p.created_at} for p in rows]


@router.get("/v1/orgs/{org_id}/payments/summary")
async def summary(form_id: uuid.UUID | None = None,
                  ctx: Ctx = Depends(require_permission("payments:read"))) -> dict[str, Any]:
    return await service.summary(ctx.db, form_id)


@router.get("/v1/orgs/{org_id}/forms/{form_id}/tickets/offline-bundle")
async def offline_bundle(form_id: uuid.UUID, ctx: Ctx = Depends(require_permission("tickets:scan"))
                         ) -> dict[str, Any]:
    return await service.offline_bundle(ctx.db, form_id)


@router.post("/v1/orgs/{org_id}/tickets/scan")
async def scan(body: ScanIn, ctx: Ctx = Depends(require_permission("tickets:scan"))) -> dict[str, Any]:
    return await service.scan(ctx.db, body.token, ctx.user_id)


@router.post("/v1/orgs/{org_id}/tickets/sync")
async def sync(body: SyncIn, ctx: Ctx = Depends(require_permission("tickets:scan"))) -> dict[str, Any]:
    return await service.sync_scans(ctx.db, body.scans, ctx.user_id)


@router.get("/v1/orgs/{org_id}/forms/{form_id}/tickets")
async def form_tickets(form_id: uuid.UUID, ctx: Ctx = Depends(require_permission("responses:read"))
                       ) -> dict[str, Any]:
    cats = (await ctx.db.execute(select(TicketCategory).where(TicketCategory.form_id == form_id))).scalars()
    return {"categories": [{"id": c.id, "name": c.name, "quota": c.quota, "issued": c.issued,
                            "reserved": c.reserved, "price": c.price} for c in cats]}
