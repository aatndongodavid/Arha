"""Dev helper for the end to end check: the simulated operator approves every pending fake charge
by re-reading the real provider status path (get_charge), exactly like a webhook would trigger."""
import asyncio

from sqlalchemy import text

from arha.db.session import app_tx, platform_tx
from arha.modules.payments import service
from arha.modules.payments.adapters.base import ChargeStatus
from arha.modules.payments.adapters.fake import FAKE
from arha.modules.payments.models import Payment
import arha.workers.tasks  # noqa: F401
from sqlalchemy import select


async def main() -> None:
    async with platform_tx() as db:
        rows = (await db.execute(text("select id, organization_id, provider_ref, amount, currency from payments "
                                      "where status = 'pending'"))).all()
    for pid, oid, ref, amount, currency in rows:
        async def paid(_ref: str, a: int = amount, c: str = currency, r: str = ref) -> ChargeStatus:
            return ChargeStatus(provider_ref=r, status="succeeded", amount=a, currency=c, reference=None)
        FAKE.get_charge = paid  # type: ignore[method-assign]
        async with app_tx(org_id=oid) as db:
            p = (await db.execute(select(Payment).where(Payment.id == pid).with_for_update())).scalar_one()
            await service.confirm_with_provider(db, p, source="webhook")


asyncio.run(main())
