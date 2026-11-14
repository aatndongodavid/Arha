"""Campay adapter (fallback provider, master prompt 9.2). No documented platform fee split:
Arha's commission is counted in usage_counters and invoiced monthly.

VERIFY every path and field below against the Campay documentation before production use.
"""

from __future__ import annotations

import json
from collections.abc import Mapping
from datetime import datetime
from typing import Any

import httpx

from arha.modules.payments.adapters.base import (
    ChargeInitiated,
    ChargeRequest,
    ChargeStatus,
    ConnectedAccount,
    KycPayload,
    OrgRef,
    ProviderError,
    ProviderStatus,
    ProviderTxn,
    RefundResult,
    SignatureError,
    WebhookEvent,
)
from arha.settings import get_settings

_STATUS: dict[str, ProviderStatus] = {"SUCCESSFUL": "succeeded", "FAILED": "failed", "PENDING": "pending"}  # VERIFY


class Campay:
    code = "campay"
    supports_platform_fee = False

    def __init__(self, client: httpx.AsyncClient | None = None) -> None:
        s = get_settings()
        if not s.campay_username or not s.campay_password:
            raise ProviderError("provider_not_configured", retryable=False)
        self.username = s.campay_username.get_secret_value()
        self.password = s.campay_password.get_secret_value()
        self.client = client or httpx.AsyncClient(base_url=s.campay_base_url, timeout=15.0)
        self._token: str | None = None

    async def _auth(self) -> dict[str, str]:
        if self._token is None:
            # VERIFY: token endpoint `/token/` with username and password (application credentials).
            data = await self._call("POST", "/token/", json={"username": self.username, "password": self.password},
                                    auth=False)
            self._token = str(data.get("token"))
        return {"Authorization": f"Token {self._token}"}

    async def _call(self, method: str, path: str, *, auth: bool = True, **kwargs: Any) -> dict[str, Any]:
        headers = await self._auth() if auth else {}
        try:
            resp = await self.client.request(method, path, headers=headers, **kwargs)
        except httpx.HTTPError as exc:
            raise ProviderError("provider_unavailable") from exc
        if resp.status_code >= 500:
            raise ProviderError("provider_unavailable")
        if resp.status_code >= 400:
            raise ProviderError(f"provider_rejected_{resp.status_code}", retryable=False)
        data: dict[str, Any] = resp.json()
        return data

    async def create_connected_account(self, org: OrgRef, kyc: KycPayload) -> ConnectedAccount:
        # Campay has no connected accounts: funds settle on the organisation's own Campay application,
        # whose credentials are configured for it. VERIFY the onboarding model with Campay.
        return ConnectedAccount(provider_account_id=f"campay:{org.id}", status="pending")

    async def get_connected_account(self, provider_account_id: str) -> ConnectedAccount:
        return ConnectedAccount(provider_account_id=provider_account_id, status="pending")

    async def initiate_charge(self, req: ChargeRequest) -> ChargeInitiated:
        # VERIFY: `/collect/` with amount as string, `from` without the plus sign, external_reference.
        data = await self._call("POST", "/collect/", json={
            "amount": str(req.amount), "currency": req.currency, "from": req.msisdn.lstrip("+"),
            "description": req.description[:100], "external_reference": req.reference})
        ref = data.get("reference")
        if not ref:
            raise ProviderError("provider_bad_response")
        return ChargeInitiated(provider_ref=str(ref), status="pending", raw={"operator": data.get("operator")})

    async def get_charge(self, provider_ref: str) -> ChargeStatus:
        data = await self._call("GET", f"/transaction/{provider_ref}/")  # VERIFY
        return ChargeStatus(provider_ref=provider_ref, status=_STATUS.get(str(data.get("status")), "pending"),
                            amount=int(float(data["amount"])) if data.get("amount") else None,
                            currency=data.get("currency"), reference=data.get("external_reference"),
                            raw={"status": data.get("status")})

    def verify_webhook(self, headers: Mapping[str, str], body: bytes) -> WebhookEvent:
        # VERIFY: Campay signs callbacks with a JWT in `signature` using the webhook key. Until verified,
        # webhooks are treated as untrusted hints and the status is always re-read with get_charge.
        try:
            payload = json.loads(body or b"{}")
        except json.JSONDecodeError as exc:
            raise SignatureError() from exc
        return WebhookEvent(provider_ref=payload.get("reference"), reference=payload.get("external_reference"),
                            status=None, raw={})

    async def refund(self, provider_ref: str, amount: int) -> RefundResult:
        raise ProviderError("refund_not_supported", retryable=False)

    async def list_transactions(self, since: datetime, until: datetime) -> list[ProviderTxn]:
        data = await self._call("POST", "/history/", json={  # VERIFY
            "start_date": since.date().isoformat(), "end_date": until.date().isoformat()})
        return [ProviderTxn(provider_ref=str(tx.get("reference")), reference=tx.get("external_reference"),
                            amount=int(float(tx.get("amount", 0))), currency=str(tx.get("currency", "XAF")),
                            status=_STATUS.get(str(tx.get("status")), "pending"))
                for tx in data.get("data", [])]
