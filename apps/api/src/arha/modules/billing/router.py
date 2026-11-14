from __future__ import annotations

import uuid
from typing import Any, Literal

from fastapi import APIRouter, Depends, Header, Response
from pydantic import BaseModel, ConfigDict, Field

from arha.core import idempotency
from arha.core.context import Ctx, public_route, require_permission
from arha.core.errors import NotFound
from arha.core.plans import get_plans
from arha.modules.billing import service
from arha.modules.billing.models import Invoice
from arha.modules.trust import service as trust

router = APIRouter(tags=["billing"])


class SubscribeIn(BaseModel):
    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)
    plan: Literal["pro", "equipe", "terrain"]
    period: Literal["monthly", "yearly"] = "monthly"
    msisdn: str = Field(min_length=8, max_length=20)


def _public_plan(cfg: Any, code: str) -> dict[str, Any]:
    p = cfg.plans[code]
    limit, period = cfg.responses_limit(code)
    return {"code": code, "price": p.price, "price_once": p.price_once, "duration_days": p.duration_days,
            "price_monthly": p.price_monthly, "price_monthly_from": p.price_monthly_from,
            "price_yearly": p.price_yearly if p.price_yearly is not None else (
                cfg.yearly_price(code) if p.price_monthly else None),
            "responses": limit, "responses_period": period, "members": cfg.limit(code, "members"),
            "reviewers": cfg.limit(code, "reviewers"), "enumerators": cfg.limit(code, "enumerators"),
            "storage_gb": cfg.limit(code, "storage_gb"), "payment_fee_bps": p.payment_fee_bps,
            "exports": sorted(cfg.exports_of(code)), "features": sorted(cfg.features_of(code)), "custom": p.custom}


@router.get("/v1/plans")
async def plans(ctx: Ctx = Depends(public_route)) -> dict[str, Any]:
    """The price grid for the pricing page and the upgrade screen, read from config/plans.yaml (F-FAC-05)."""
    cfg = get_plans()
    return {"currency": cfg.currency, "annual_months_charged": cfg.annual_months_charged,
            "pioneer": cfg.pioneer.model_dump(), "plans": {code: _public_plan(cfg, code) for code in cfg.plans},
            "addons": {k: v.model_dump() for k, v in cfg.addons.items()},
            "studies": {k: v.model_dump() for k, v in cfg.studies.items()}}


@router.get("/v1/orgs/{org_id}/billing")
async def billing(ctx: Ctx = Depends(require_permission("org:read"))) -> dict[str, Any]:
    cfg = get_plans()
    sub = await service.active_subscription(ctx.db)
    student_pass = await service.current_pass(ctx.db)
    period = service.response_period(ctx.org)
    used = await service.usage(ctx.db, period=period)
    limit, _ = cfg.responses_limit(ctx.org.plan_code)
    invoices = await service.list_invoices(ctx.db) if ctx.role in ("owner", "admin") else []
    return {"plan": ctx.org.plan_code, "usage": {"responses": used, "limit": limit, "period": period,
                                                 "quota_exceeded_at": ctx.org.quota_exceeded_at},
            "subscription": None if sub is None else {
                "id": sub.id, "plan": sub.plan_code, "period": sub.billing_period, "status": sub.status,
                "period_end": sub.period_end, "amount": sub.amount, "pioneer": sub.pioneer,
                "discount_bps": sub.discount_bps},
            "pass": None if student_pass is None else {
                "institution": student_pass.institution, "level": student_pass.level,
                "starts_at": student_pass.starts_at, "ends_at": student_pass.ends_at},
            "invoices": [{"id": i.id, "number": i.number, "amount": i.amount, "currency": i.currency,
                          "kind": i.kind, "issued_at": i.issued_at} for i in invoices],
            "pioneer_seats_left": await service.pioneer_seats_left(ctx.db)}


@router.post("/v1/orgs/{org_id}/billing/subscribe", status_code=201)
async def subscribe(body: SubscribeIn, idempotency_key: str | None = Header(default=None, alias="Idempotency-Key"),
                    ctx: Ctx = Depends(require_permission("billing:manage"))) -> dict[str, Any]:
    from arha.modules.payments.service import start_platform_payment

    key = idempotency.require_key(idempotency_key)
    sub = await service.create_subscription(ctx.db, ctx.org, body.plan, body.period)
    await trust.audit(ctx.db, "billing.subscribe_started", org_id=ctx.org_id, actor_id=ctx.user_id,
                      metadata={"plan": body.plan, "period": body.period, "amount": sub.amount})
    # The subscription is committed with the payment row before the provider can confirm anything.
    _, view = await start_platform_payment(ctx, org=ctx.org, amount=sub.amount, msisdn=body.msisdn,
                                                    idempotency_key=key,
                                                    description=f"Arha {body.plan} {body.period}",
                                                    purpose="subscription", link_id=sub.id)
    return {"subscription_id": sub.id, "amount": sub.amount, "discount_bps": sub.discount_bps,
            "pioneer": sub.pioneer, "payment": view}


class PassIn(BaseModel):
    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)
    institution: str = Field(min_length=2, max_length=200)
    level: Literal["licence", "master", "doctorat", "autre"]
    msisdn: str = Field(min_length=8, max_length=20)
    ambassador_code: str | None = Field(default=None, max_length=32)


@router.post("/v1/orgs/{org_id}/billing/pass", status_code=201)
async def buy_pass(body: PassIn, idempotency_key: str | None = Header(default=None, alias="Idempotency-Key"),
                   ctx: Ctx = Depends(require_permission("billing:manage"))) -> dict[str, Any]:
    """F-FAC-06: the student buys a Pass Mémoire by Mobile Money, on Arha's merchant account."""
    from arha.modules.payments.service import start_platform_payment

    key = idempotency.require_key(idempotency_key)
    student_pass = await service.create_pass(ctx.db, ctx.org, user_id=ctx.user_id, institution=body.institution,
                                             level=body.level, ambassador_code=body.ambassador_code)
    await trust.audit(ctx.db, "billing.pass_started", org_id=ctx.org_id, actor_id=ctx.user_id,
                      metadata={"level": body.level, "amount": student_pass.amount})
    _, view = await start_platform_payment(ctx, org=ctx.org, amount=student_pass.amount, msisdn=body.msisdn,
                                           idempotency_key=key, description="Arha Pass Memoire", purpose="pass",
                                           link_id=student_pass.id)
    return {"pass_id": student_pass.id, "amount": student_pass.amount, "payment": view}


@router.get("/v1/orgs/{org_id}/billing/invoices/{invoice_id}.pdf")
async def invoice_pdf(invoice_id: uuid.UUID, ctx: Ctx = Depends(require_permission("billing:manage"))) -> Response:
    from arha.modules.billing.documents import render_invoice

    inv = await ctx.db.get(Invoice, invoice_id)
    if inv is None:
        raise NotFound()
    return Response(render_invoice(inv, ctx.org, ctx.locale), media_type="application/pdf",
                    headers={"Content-Disposition": f'attachment; filename="{inv.number}.pdf"'})
