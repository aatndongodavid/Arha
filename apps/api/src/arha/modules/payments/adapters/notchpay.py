"""Notch Pay adapter (primary provider, master prompt 9.2).

IMPORTANT: written without access to https://developer.notchpay.co (blocked by the build network).
Every field, header and path below is marked VERIFY and must be confirmed against the official
documentation, then exercised with the manual sandbox test (tests/integration/test_notchpay_sandbox.py)
before any production use.
"""

from __future__ import annotations

import hashlib
import hmac
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

# VERIFY: status vocabulary returned by Notch Pay for a payment.
_STATUS: dict[str, ProviderStatus] = {
    "pending": "pending", "processing": "pending", "complete": "succeeded", "completed": "succeeded",
    "success": "succeeded", "failed": "failed", "canceled": "failed", "cancelled": "failed",
    "rejected": "failed", "expired": "expired",
}
# VERIFY: Cameroon mobile money channels documented as cm.mtn, cm.orange, cm.mobile (master prompt 9.2).
_CHANNEL = {"mtn": "cm.mtn", "orange": "cm.orange", "auto": "cm.mobile"}


class NotchPay:
    code = "notchpay"
    supports_platform_fee = True

    def __init__(self, client: httpx.AsyncClient | None = None) -> None:
        s = get_settings()
        if not s.notchpay_public_key:
            raise ProviderError("provider_not_configured", retryable=False)
        self.public_key = s.notchpay_public_key.get_secret_value()
        self.private_key = s.notchpay_private_key.get_secret_value() if s.notchpay_private_key else ""
        self.webhook_secret = s.notchpay_webhook_secret.get_secret_value() if s.notchpay_webhook_secret else ""
        self.client = client or httpx.AsyncClient(base_url=s.notchpay_base_url, timeout=15.0)

    def _headers(self, *, grant: bool = False, idempotency_key: str | None = None) -> dict[str, str]:
        # VERIFY: public key sent in `Authorization`, private key in `X-Grant` for privileged calls.
        headers = {"Authorization": self.public_key, "Accept": "application/json"}
        if grant:
            headers["X-Grant"] = self.private_key
        if idempotency_key:
            headers["Idempotency-Key"] = idempotency_key  # VERIFY: idempotency header support
        return headers

    async def _call(self, method: str, path: str, **kwargs: Any) -> dict[str, Any]:
        try:
            resp = await self.client.request(method, path, **kwargs)
        except httpx.HTTPError as exc:
            raise ProviderError("provider_unavailable") from exc
        if resp.status_code >= 500:
            raise ProviderError("provider_unavailable")
        if resp.status_code >= 400:
            raise ProviderError(f"provider_rejected_{resp.status_code}", retryable=False)
        data: dict[str, Any] = resp.json()
        return data

    async def create_connected_account(self, org: OrgRef, kyc: KycPayload) -> ConnectedAccount:
        # VERIFY: Sync for platforms endpoint and payload for connected accounts.
        data = await self._call("POST", "/sync/accounts", headers=self._headers(grant=True), json={
            "name": kyc.business_name, "email": kyc.email, "phone": kyc.phone, "country": org.country,
            "reference": org.id})
        account = data.get("account") or data
        return ConnectedAccount(provider_account_id=str(account.get("id")),
                                status="verified" if account.get("status") in ("active", "verified") else "pending",
                                onboarding_url=account.get("onboarding_url"))  # VERIFY

    async def get_connected_account(self, provider_account_id: str) -> ConnectedAccount:
        data = await self._call("GET", f"/sync/accounts/{provider_account_id}", headers=self._headers(grant=True))
        account = data.get("account") or data  # VERIFY
        status = account.get("status")
        return ConnectedAccount(provider_account_id=provider_account_id,
                                status="verified" if status in ("active", "verified") else (
                                    "suspended" if status == "suspended" else "pending"),
                                onboarding_url=account.get("onboarding_url"))

    async def initiate_charge(self, req: ChargeRequest) -> ChargeInitiated:
        # Step 1: create the payment. VERIFY: path `/payments`, fields amount, currency, reference,
        # description, callback, customer.phone, and the platform fee fields for Sync.
        body: dict[str, Any] = {"amount": req.amount, "currency": req.currency, "reference": req.reference,
                                "description": req.description[:200], "callback": req.callback_url,
                                "customer": {"phone": req.msisdn}}
        if req.connected_account_id:
            body["application_fee"] = req.platform_fee  # VERIFY: name of the platform fee field
            body["destination"] = req.connected_account_id  # VERIFY: name of the destination field
        created = await self._call("POST", "/payments", json=body,
                                   headers=self._headers(idempotency_key=req.idempotency_key))
        tx = created.get("transaction") or created
        ref = tx.get("reference") or tx.get("id")  # VERIFY: which identifier to keep as provider_ref
        if not ref:
            raise ProviderError("provider_bad_response")
        # Step 2: process the mobile money charge. VERIFY: path and payload shape.
        processed = await self._call("POST", f"/payments/{ref}", headers=self._headers(),
                                     json={"channel": _CHANNEL[req.channel], "data": {"phone": req.msisdn}})
        ptx = processed.get("transaction") or tx
        return ChargeInitiated(provider_ref=str(ref), status=_STATUS.get(str(ptx.get("status")), "pending"),
                               raw={"status": ptx.get("status")})

    async def get_charge(self, provider_ref: str) -> ChargeStatus:
        data = await self._call("GET", f"/payments/{provider_ref}", headers=self._headers())  # VERIFY
        tx = data.get("transaction") or data
        return ChargeStatus(provider_ref=provider_ref, status=_STATUS.get(str(tx.get("status")), "pending"),
                            amount=int(tx["amount"]) if tx.get("amount") is not None else None,
                            currency=tx.get("currency"), reference=tx.get("merchant_reference") or tx.get(
                                "trxref"),  # VERIFY: field holding our reference
                            raw={"status": tx.get("status")})

    def verify_webhook(self, headers: Mapping[str, str], body: bytes) -> WebhookEvent:
        # VERIFY: header name `x-notch-signature`, HMAC-SHA256 hex digest of the raw body with the
        # webhook hash secret.
        lower = {k.lower(): v for k, v in headers.items()}
        signature = lower.get("x-notch-signature", "")
        expected = hmac.new(self.webhook_secret.encode(), body, hashlib.sha256).hexdigest()
        if not self.webhook_secret or not hmac.compare_digest(signature, expected):
            raise SignatureError()
        payload = json.loads(body)
        data = payload.get("data") or {}
        return WebhookEvent(provider_ref=data.get("reference") or data.get("id"),
                            reference=data.get("merchant_reference") or data.get("trxref"),  # VERIFY
                            status=_STATUS.get(str(data.get("status"))), raw={"event": payload.get("event")})

    async def refund(self, provider_ref: str, amount: int) -> RefundResult:
        # VERIFY: refunds are V2 (F-PAY-11); endpoint to confirm.
        data = await self._call("POST", f"/payments/{provider_ref}/refund", headers=self._headers(grant=True),
                                json={"amount": amount})
        return RefundResult(provider_ref=provider_ref,
                            status="succeeded" if data.get("status") in ("complete", "success") else "pending")

    async def list_transactions(self, since: datetime, until: datetime) -> list[ProviderTxn]:
        # VERIFY: listing endpoint, date filters and pagination.
        out: list[ProviderTxn] = []
        page = 1
        while page < 50:
            data = await self._call("GET", "/payments", headers=self._headers(), params={
                "date_start": since.date().isoformat(), "date_end": until.date().isoformat(), "page": page,
                "perpage": 100})
            items = data.get("items") or data.get("transactions") or []
            for tx in items:
                out.append(ProviderTxn(provider_ref=str(tx.get("reference")), reference=tx.get("merchant_reference"),
                                       amount=int(tx.get("amount", 0)), currency=str(tx.get("currency", "XAF")),
                                       status=_STATUS.get(str(tx.get("status")), "pending")))
            if len(items) < 100:
                break
            page += 1
        return out
