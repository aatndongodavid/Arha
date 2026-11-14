from __future__ import annotations

import uuid

from arha.core.jobs import job
from arha.db.session import app_tx
from arha.modules.integrations import service
from arha.modules.integrations.models import WebhookDelivery


@job("integrations.deliver", retry=0)
async def deliver(org_id: str, delivery_id: str) -> None:
    async with app_tx(org_id=uuid.UUID(org_id)) as db:
        delivery = await db.get(WebhookDelivery, uuid.UUID(delivery_id), with_for_update=True)
        if delivery is not None:
            await service.deliver(db, delivery)
