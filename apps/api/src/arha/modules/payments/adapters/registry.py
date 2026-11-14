"""Provider selection by configuration only (F-PAY-10)."""

from __future__ import annotations

from arha.modules.payments.adapters.base import PaymentProvider, ProviderError
from arha.settings import get_settings

_INSTANCES: dict[str, PaymentProvider] = {}


def resolve_code(requested: str | None) -> str:
    override = get_settings().payment_provider_override
    return override or requested or "notchpay"


def get_provider(code: str) -> PaymentProvider:
    code = resolve_code(code)
    if code not in _INSTANCES:
        if code == "fake":
            if get_settings().arha_env == "prod":
                raise ProviderError("provider_not_configured", retryable=False)
            from arha.modules.payments.adapters.fake import FAKE
            _INSTANCES[code] = FAKE
        elif code == "notchpay":
            from arha.modules.payments.adapters.notchpay import NotchPay
            _INSTANCES[code] = NotchPay()
        elif code == "campay":
            from arha.modules.payments.adapters.campay import Campay
            _INSTANCES[code] = Campay()
        else:
            raise ProviderError("provider_unknown", retryable=False)
    return _INSTANCES[code]
