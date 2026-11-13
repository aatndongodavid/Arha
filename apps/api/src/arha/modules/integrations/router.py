from __future__ import annotations

import uuid
from typing import Any

from fastapi import APIRouter, Depends
from pydantic import BaseModel, ConfigDict, Field
from sqlalchemy import select

from arha.core.context import Ctx, require_permission
from arha.core.errors import NotFound
from arha.core.features import require_feature
from arha.modules.integrations import service
from arha.modules.integrations.models import WebhookDelivery, WebhookEndpoint
from arha.modules.trust import service as trust

router = APIRouter(prefix="/v1/orgs/{org_id}/webhooks", tags=["integrations"])


class EndpointIn(BaseModel):
    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)
    url: str = Field(min_length=10, max_length=2048)
    form_id: uuid.UUID | None = None


@router.get("")
async def list_endpoints(ctx: Ctx = Depends(require_permission("integrations:manage"))) -> list[dict[str, Any]]:
    rows = (await ctx.db.execute(select(WebhookEndpoint).order_by(WebhookEndpoint.created_at))).scalars()
    return [{"id": e.id, "url": e.url, "form_id": e.form_id, "events": e.events, "active": e.active} for e in rows]


@router.post("", status_code=201)
async def create(body: EndpointIn, ctx: Ctx = Depends(require_permission("integrations:manage"))) -> dict[str, Any]:
    require_feature(ctx.org, "webhooks")
    ep, secret = await service.create_endpoint(ctx.db, body.url, body.form_id)
    await trust.audit(ctx.db, "webhook.created", org_id=ctx.org_id, actor_id=ctx.user_id, target_type="webhook",
                      target_id=ep.id)
    return {"id": ep.id, "url": ep.url, "secret": secret}  # the secret is shown once


@router.delete("/{endpoint_id}", status_code=204)
async def delete(endpoint_id: uuid.UUID, ctx: Ctx = Depends(require_permission("integrations:manage"))) -> None:
    ep = await ctx.db.get(WebhookEndpoint, endpoint_id)
    if ep is None:
        raise NotFound()
    ep.active = False


@router.get("/{endpoint_id}/deliveries")
async def deliveries(endpoint_id: uuid.UUID, ctx: Ctx = Depends(require_permission("integrations:manage"))
                     ) -> list[dict[str, Any]]:
    """F-REP-06: the delivery log is visible to the organisation."""
    rows = (await ctx.db.execute(select(WebhookDelivery).where(WebhookDelivery.endpoint_id == endpoint_id)
                                 .order_by(WebhookDelivery.created_at.desc()).limit(100))).scalars()
    return [{"id": d.id, "event": d.event, "attempt": d.attempt, "status_code": d.status_code, "error": d.error,
             "delivered_at": d.delivered_at, "failed_at": d.failed_at, "next_retry_at": d.next_retry_at,
             "created_at": d.created_at} for d in rows]
