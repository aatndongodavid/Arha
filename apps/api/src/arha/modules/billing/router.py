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
    plan: Literal["pro", "business", "terrain"]
    period: Literal["monthly", "yearly"] = "monthly"
    msisdn: str = Field(min_length=8, max_length=20)


@router.get("/v1/plans")
async def plans(ctx: Ctx = Depends(public_route)) -> dict[str, Any]:
    """Prices for the pricing page and the upgrade screen, read from config/plans.yaml (F-FAC-05)."""
    cfg = get_plans()
    return {"currency": cfg.currency, "annual_months_charged": cfg.annual_months_charged,
            "pioneer": cfg.pioneer.model_dump(), "nonprofit_discount": cfg.nonprofit_discount.model_dump(),
            "plans": {code: {**p.model_dump(exclude={"features", "extra_features", "inherits"}),
                             "features": sorted(cfg.features_of(code)),
                             "price_yearly": p.price_yearly if p.price_yearly is not None else (
                                 cfg.yearly_price(code) if p.price_monthly else None)}
                      for code, p in cfg.plans.items()},
            "addons": {k: v.model_dump() for k, v in cfg.addons.items()},
            "services": {k: v.model_dump() for k, v in cfg.services.items()}}


@router.get("/v1/orgs/{org_id}/billing")
async def billing(ctx: Ctx = Depends(require_permission("org:read"))) -> dict[str, Any]:
    cfg = get_plans()
    sub = await service.active_subscription(ctx.db)
    used = await service.usage(ctx.db)
    limit = cfg.limit(ctx.org.plan_code, "responses_per_month")
    invoices = await service.list_invoices(ctx.db) if ctx.role in ("owner", "admin") else []
    return {"plan": ctx.org.plan_code, "usage": {"responses": used, "limit": limit, "period": service.period_of(),
                                                 "quota_exceeded_at": ctx.org.quota_exceeded_at},
            "subscription": None if sub is None else {
                "id": sub.id, "plan": sub.plan_code, "period": sub.billing_period, "status": sub.status,
                "period_end": sub.period_end, "amount": sub.amount, "pioneer": sub.pioneer,
                "discount_bps": sub.discount_bps},
            "invoices": [{"id": i.id, "number": i.number, "amount": i.amount, "currency": i.currency,
                          "issued_at": i.issued_at} for i in invoices],
            "pioneer_seats_left": await service.pioneer_seats_left(ctx.db)}


@router.post("/v1/orgs/{org_id}/billing/subscribe", status_code=201)
async def subscribe(body: SubscribeIn, idempotency_key: str | None = Header(default=None, alias="Idempotency-Key"),
                    ctx: Ctx = Depends(require_permission("billing:manage"))) -> dict[str, Any]:
    from arha.modules.payments.service import start_platform_payment

    from arha.db.session import app_tx
    from arha.modules.orgs.service import get_org

    key = idempotency.require_key(idempotency_key)
    assert ctx.org_id
    # Committed in its own transaction: the subscription must exist before the provider confirms.
    async with app_tx(org_id=ctx.org_id, user_id=ctx.user_id) as db:
        sub = await service.create_subscription(db, await get_org(db, ctx.org_id), body.plan, body.period)
    payment_id, view = await start_platform_payment(org_id=ctx.org_id, org=ctx.org, amount=sub.amount,
                                                    msisdn=body.msisdn, idempotency_key=key,
                                                    description=f"Arha {body.plan} {body.period}",
                                                    subscription_id=sub.id)
    async with app_tx(org_id=ctx.org_id, user_id=ctx.user_id) as db:
        await trust.audit(db, "billing.subscribe_started", org_id=ctx.org_id, actor_id=ctx.user_id,
                          metadata={"plan": body.plan, "period": body.period, "amount": sub.amount})
    return {"subscription_id": sub.id, "amount": sub.amount, "discount_bps": sub.discount_bps,
            "pioneer": sub.pioneer, "payment": view}


@router.get("/v1/orgs/{org_id}/billing/invoices/{invoice_id}.pdf")
async def invoice_pdf(invoice_id: uuid.UUID, ctx: Ctx = Depends(require_permission("billing:manage"))) -> Response:
    from arha.modules.billing.documents import render_invoice

    inv = await ctx.db.get(Invoice, invoice_id)
    if inv is None:
        raise NotFound()
    return Response(render_invoice(inv, ctx.org, ctx.locale), media_type="application/pdf",
                    headers={"Content-Disposition": f'attachment; filename="{inv.number}.pdf"'})
