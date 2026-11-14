"""Payment provider interface (master prompt 9.1). Business code depends on this protocol only."""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass, field
from datetime import datetime
from typing import Any, Literal, Protocol

ProviderStatus = Literal["pending", "succeeded", "failed", "expired"]


@dataclass(frozen=True)
class OrgRef:
    id: str
    name: str
    country: str


@dataclass(frozen=True)
class KycPayload:
    email: str
    business_name: str
    phone: str | None = None


@dataclass(frozen=True)
class ConnectedAccount:
    provider_account_id: str
    status: Literal["pending", "verified", "suspended"]
    onboarding_url: str | None = None


@dataclass(frozen=True)
class ChargeRequest:
    idempotency_key: str
    amount: int
    currency: str
    msisdn: str  # E.164, never logged
    channel: Literal["mtn", "orange", "auto"]
    connected_account_id: str | None
    platform_fee: int
    description: str
    reference: str  # Arha payment id
    callback_url: str


@dataclass(frozen=True)
class ChargeInitiated:
    provider_ref: str
    status: ProviderStatus
    raw: dict[str, Any] = field(default_factory=dict)


@dataclass(frozen=True)
class ChargeStatus:
    provider_ref: str
    status: ProviderStatus
    amount: int | None
    currency: str | None
    reference: str | None
    failure_reason: str | None = None
    raw: dict[str, Any] = field(default_factory=dict)


@dataclass(frozen=True)
class WebhookEvent:
    provider_ref: str | None
    reference: str | None
    status: ProviderStatus | None
    raw: dict[str, Any] = field(default_factory=dict)


@dataclass(frozen=True)
class RefundResult:
    provider_ref: str
    status: Literal["pending", "succeeded", "failed"]


@dataclass(frozen=True)
class ProviderTxn:
    provider_ref: str
    reference: str | None
    amount: int
    currency: str
    status: ProviderStatus
    created_at: datetime | None = None


class ProviderError(Exception):
    """Transient or functional provider failure. The message never contains personal data."""

    def __init__(self, code: str, retryable: bool = True) -> None:
        super().__init__(code)
        self.code = code
        self.retryable = retryable


class SignatureError(Exception):
    pass


class PaymentProvider(Protocol):
    code: str
    supports_platform_fee: bool

    async def create_connected_account(self, org: OrgRef, kyc: KycPayload) -> ConnectedAccount: ...
    async def get_connected_account(self, provider_account_id: str) -> ConnectedAccount: ...
    async def initiate_charge(self, req: ChargeRequest) -> ChargeInitiated: ...
    async def get_charge(self, provider_ref: str) -> ChargeStatus: ...
    def verify_webhook(self, headers: Mapping[str, str], body: bytes) -> WebhookEvent: ...
    async def refund(self, provider_ref: str, amount: int) -> RefundResult: ...
    async def list_transactions(self, since: datetime, until: datetime) -> list[ProviderTxn]: ...
