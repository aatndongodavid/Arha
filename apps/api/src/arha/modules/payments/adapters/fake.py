"""FakeNotchPay: in-process simulator used in tests and local development (master prompt section 15).

Behaviour is driven by the phone number so end to end flows are deterministic:
  ending in 0000 -> the charge fails
  ending in 9999 -> no webhook is ever sent (exercises polling and expiry)
  anything else  -> the charge stays pending until `approve()` (tests) or the dev auto-approval delay
"""

from __future__ import annotations

import hashlib
import hmac
import json
from collections.abc import Mapping
from dataclasses import dataclass
from datetime import datetime
from typing import Any

from arha.core import clock
from arha.core.ids import uuid7
from arha.modules.payments.adapters.base import (
    ChargeInitiated,
    ChargeRequest,
    ChargeStatus,
    ConnectedAccount,
    KycPayload,
    OrgRef,
    ProviderError,
    ProviderTxn,
    RefundResult,
    SignatureError,
    WebhookEvent,
)

FAKE_WEBHOOK_SECRET = "fake-webhook-secret"  # noqa: S105 - test double only


@dataclass
class FakeCharge:
    ref: str
    reference: str
    amount: int
    currency: str
    platform_fee: int
    connected_account_id: str | None
    status: str
    silent: bool
    created_at: datetime


class FakeNotchPay:
    code = "fake"
    supports_platform_fee = True

    def __init__(self) -> None:
        self.charges: dict[str, FakeCharge] = {}
        self.by_idempotency: dict[str, str] = {}
        self.calls: list[str] = []
        self.fail_next_initiate = False

    def reset(self) -> None:
        self.__init__()  # type: ignore[misc]

    async def create_connected_account(self, org: OrgRef, kyc: KycPayload) -> ConnectedAccount:
        self.calls.append("create_connected_account")
        return ConnectedAccount(provider_account_id=f"acct_fake_{org.id[:8]}", status="verified",
                                onboarding_url=None)

    async def get_connected_account(self, provider_account_id: str) -> ConnectedAccount:
        return ConnectedAccount(provider_account_id=provider_account_id, status="verified")

    async def initiate_charge(self, req: ChargeRequest) -> ChargeInitiated:
        self.calls.append("initiate_charge")
        if self.fail_next_initiate:
            self.fail_next_initiate = False
            raise ProviderError("provider_unavailable")
        if req.idempotency_key in self.by_idempotency:  # provider side idempotency
            ref = self.by_idempotency[req.idempotency_key]
            return ChargeInitiated(provider_ref=ref, status="pending")
        ref = f"fake_{uuid7().hex[:20]}"
        status = "failed" if req.msisdn.endswith("0000") else "pending"
        self.charges[ref] = FakeCharge(ref, req.reference, req.amount, req.currency, req.platform_fee,
                                       req.connected_account_id, status, req.msisdn.endswith("9999"), clock.now())
        self.by_idempotency[req.idempotency_key] = ref
        return ChargeInitiated(provider_ref=ref, status="failed" if status == "failed" else "pending")

    def approve(self, ref: str, *, amount: int | None = None) -> bytes:
        charge = self.charges[ref]
        charge.status = "succeeded"
        if amount is not None:
            charge.amount = amount
        return self.webhook_body(ref)

    def decline(self, ref: str) -> bytes:
        self.charges[ref].status = "failed"
        return self.webhook_body(ref)

    def webhook_body(self, ref: str) -> bytes:
        c = self.charges[ref]
        return json.dumps({"event": f"payment.{c.status}", "data": {"ref": c.ref, "reference": c.reference,
                                                                     "status": c.status, "amount": c.amount}}).encode()

    @staticmethod
    def sign(body: bytes) -> str:
        return hmac.new(FAKE_WEBHOOK_SECRET.encode(), body, hashlib.sha256).hexdigest()

    async def get_charge(self, provider_ref: str) -> ChargeStatus:
        self.calls.append("get_charge")
        c = self.charges.get(provider_ref)
        if c is None:
            raise ProviderError("unknown_charge", retryable=False)
        return ChargeStatus(provider_ref=c.ref, status=c.status, amount=c.amount,  # type: ignore[arg-type]
                            currency=c.currency, reference=c.reference)

    def verify_webhook(self, headers: Mapping[str, str], body: bytes) -> WebhookEvent:
        sig = {k.lower(): v for k, v in headers.items()}.get("x-fake-signature", "")
        if not hmac.compare_digest(sig, self.sign(body)):
            raise SignatureError()
        data: dict[str, Any] = json.loads(body).get("data", {})
        return WebhookEvent(provider_ref=data.get("ref"), reference=data.get("reference"),
                            status=data.get("status"), raw={"event": json.loads(body).get("event")})

    async def refund(self, provider_ref: str, amount: int) -> RefundResult:
        return RefundResult(provider_ref=provider_ref, status="succeeded")

    async def list_transactions(self, since: datetime, until: datetime) -> list[ProviderTxn]:
        return [ProviderTxn(provider_ref=c.ref, reference=c.reference, amount=c.amount, currency=c.currency,
                            status=c.status, created_at=c.created_at)  # type: ignore[arg-type]
                for c in self.charges.values() if since <= c.created_at <= until]


FAKE = FakeNotchPay()
