"""Strict loader for config/plans.yaml (F-FAC-05). An invalid file prevents startup."""

from __future__ import annotations

from functools import lru_cache
from pathlib import Path
from typing import Literal

import yaml
from pydantic import BaseModel, ConfigDict, Field, model_validator

from arha.settings import get_settings

Feature = Literal[
    "logic", "calculations", "tickets", "csv_export", "email_notifications_owner", "partial_responses",
    "stats_exports", "respondent_emails", "google_sheets", "webhooks", "custom_theme", "crosstabs",
    "advanced_roles", "audit_log", "custom_domain", "public_api", "approvals", "sso_google",
    "mfa_required_owner", "field_app", "quality_control", "kiosk_mode", "live_map",
]


class _Strict(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)


class Plan(_Strict):
    price_monthly: int | None = Field(default=None, ge=0)
    price_yearly: int | None = Field(default=None, ge=0)
    price_monthly_from: int | None = Field(default=None, ge=0)
    responses_per_month: int | None = Field(default=None, gt=0)
    members: int | None = Field(default=None, gt=0)
    enumerators_included: int | None = None
    enumerator_extra_monthly: int | None = None
    fee_bps: int = Field(ge=0, le=10_000)
    storage_gb: int | None = None
    max_file_mb: int | None = None
    version_history_days: int | None = None
    whatsapp_included: int | None = None
    features: list[Feature] = Field(default_factory=list)
    extra_features: list[Feature] = Field(default_factory=list)
    inherits: str | None = None
    branding_required: bool = False
    custom: bool = False


class Pioneer(_Strict):
    seats: int
    discount_bps: int
    months: int


class Nonprofit(_Strict):
    plan: str
    discount_bps: int
    cumulative: bool


class QuotaPolicy(_Strict):
    alert_at_pct: int = Field(gt=0, le=100)
    grace_hours: int = Field(ge=0)


class Renewal(_Strict):
    remind_days_before: int
    downgrade_after_days_unpaid: int


class Ambassador(_Strict):
    reward: str
    paid_after_months_paid: int


class Priced(_Strict):
    price: int = Field(ge=0)
    upfront_pct: int | None = None


class PlansConfig(_Strict):
    currency: str = Field(min_length=3, max_length=3)
    annual_months_charged: int = Field(gt=0, le=12)
    pioneer: Pioneer
    nonprofit_discount: Nonprofit
    quota_policy: QuotaPolicy
    renewal: Renewal
    ambassador: Ambassador
    payment_expiry_minutes: int = Field(gt=0)
    resume_code_days: int = Field(gt=0)
    plans: dict[str, Plan]
    addons: dict[str, Priced]
    services: dict[str, Priced]

    @model_validator(mode="after")
    def _check(self) -> PlansConfig:
        if "discovery" not in self.plans:
            raise ValueError("plan 'discovery' is required (downgrade target)")
        for code, plan in self.plans.items():
            if plan.inherits and plan.inherits not in self.plans:
                raise ValueError(f"plan {code} inherits unknown plan {plan.inherits}")
            if not plan.custom and plan.responses_per_month is None:
                raise ValueError(f"plan {code} needs responses_per_month")
            if not plan.custom and plan.price_monthly is None:
                raise ValueError(f"plan {code} needs price_monthly")
        if self.nonprofit_discount.plan not in self.plans:
            raise ValueError("nonprofit_discount.plan is unknown")
        return self

    def features_of(self, code: str) -> frozenset[str]:
        plan = self.plans[code]
        own = set(plan.features) | set(plan.extra_features)
        if plan.inherits:
            own |= self.features_of(plan.inherits)
        return frozenset(own)

    def limit(self, code: str, attr: str) -> int | None:
        plan = self.plans[code]
        value = getattr(plan, attr)
        if value is None and plan.inherits:
            return self.limit(plan.inherits, attr)
        return value  # type: ignore[no-any-return]

    def yearly_price(self, code: str) -> int:
        plan = self.plans[code]
        if plan.price_yearly is not None:
            return plan.price_yearly
        return (plan.price_monthly or 0) * self.annual_months_charged


def load_plans(path: Path) -> PlansConfig:
    return PlansConfig.model_validate(yaml.safe_load(path.read_text(encoding="utf-8")))


@lru_cache
def get_plans() -> PlansConfig:
    return load_plans(get_settings().config_dir / "plans.yaml")


class ProviderCfg(_Strict):
    estimated_fee_bps: int
    supports_platform_fee: bool


class CountryCfg(_Strict):
    currency: str
    phone_prefix: str
    providers: list[str]
    channels: list[str]
    timezone: str
    primary_provider: str | None = None
    fallback_provider: str | None = None
    active: bool = True


class CountriesConfig(_Strict):
    default_country: str
    countries: dict[str, CountryCfg]
    providers: dict[str, ProviderCfg]


@lru_cache
def get_countries() -> CountriesConfig:
    raw = yaml.safe_load((get_settings().config_dir / "countries.yaml").read_text(encoding="utf-8"))
    return CountriesConfig.model_validate(raw)
