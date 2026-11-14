"""Strict loader for config/plans.yaml (F-FAC-05, cahier des charges v1.2). An invalid file prevents startup."""

from __future__ import annotations

from functools import lru_cache
from pathlib import Path
from typing import Any, Literal

import yaml
from pydantic import BaseModel, ConfigDict, Field, model_validator

from arha.settings import get_settings

Feature = Literal[
    "logic", "calculations", "descriptive_stats", "crosstabs", "field_mode", "quality_basic", "quality_advanced",
    "assignments_quotas", "live_map", "kiosk_mode", "email_notifications_owner", "partial_responses",
    "respondent_emails", "google_sheets", "webhooks", "custom_theme", "payments", "tickets", "payment_dashboard",
    "advanced_roles", "audit_log", "custom_domain", "public_api", "approvals", "sso_google", "mfa_required_owner",
]
ExportFormat = Literal["csv", "xlsx", "sav", "dta", "r", "codebook"]
Unlimited = Literal["unlimited"]


class _Strict(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)


class Responses(_Strict):
    per_month: int | None = Field(default=None, gt=0)
    total: int | None = Field(default=None, gt=0)

    @model_validator(mode="after")
    def _one(self) -> Responses:
        if (self.per_month is None) == (self.total is None):
            raise ValueError("responses needs exactly one of per_month or total")
        return self


class Plan(_Strict):
    inherits: str | None = None
    price: int | None = Field(default=None, ge=0)              # free plan
    price_once: int | None = Field(default=None, gt=0)         # Pass Mémoire
    duration_days: int | None = Field(default=None, gt=0)
    auto_renew: bool | None = None
    price_monthly: int | None = Field(default=None, ge=0)
    price_yearly: int | None = Field(default=None, ge=0)
    price_monthly_from: int | None = Field(default=None, ge=0)
    contract: Literal["annual"] | None = None
    custom: bool = False
    responses: Responses | None = None
    members: int | None = Field(default=None, gt=0)
    reviewers: int | Unlimited | None = None
    enumerators: int | None = Field(default=None, ge=0)
    enumerator_extra_monthly: int | None = Field(default=None, ge=0)
    storage_gb: int | None = Field(default=None, gt=0)
    max_file_mb: int | None = Field(default=None, gt=0)
    version_history_days: int | None = Field(default=None, gt=0)
    whatsapp_included: int | None = Field(default=None, ge=0)
    exports: list[ExportFormat] | None = None
    features: list[Feature] = Field(default_factory=list)
    extra_features: list[Feature] = Field(default_factory=list)
    branding_required: bool | None = None
    payment_fee_bps: int = Field(ge=0, le=10_000)

    @property
    def is_one_time(self) -> bool:
        return self.price_once is not None


class Pioneer(_Strict):
    seats: int = Field(gt=0)
    discount_bps: int = Field(ge=0, le=10_000)
    months: int = Field(gt=0)
    plans: list[str]


class SupervisorProgram(_Strict):
    min_students: int = Field(gt=0)
    grants_plan: str
    duration: Literal["academic_year"]


class QuotaPolicy(_Strict):
    alert_at_pct: int = Field(gt=0, le=100)
    grace_hours: int = Field(ge=0)


class Renewal(_Strict):
    remind_days_before: int
    downgrade_after_days_unpaid: int


class Ambassador(_Strict):
    subscription_reward: Literal["one_month_of_plan"]
    paid_after_months_paid: int
    pass_reward: int = Field(ge=0)


class Priced(_Strict):
    price: int = Field(ge=0)


class Study(_Strict):
    price: int = Field(gt=0)
    upfront_pct: int = Field(gt=0, le=100)
    brand: Literal["services", "etudes"]


class PlansConfig(_Strict):
    currency: str = Field(min_length=3, max_length=3)
    annual_months_charged: int = Field(gt=0, le=12)
    pioneer: Pioneer
    supervisor_program: SupervisorProgram
    quota_policy: QuotaPolicy
    renewal: Renewal
    ambassador: Ambassador
    payment_expiry_minutes: int = Field(gt=0)
    resume_code_days: int = Field(gt=0)
    plans: dict[str, Plan]
    addons: dict[str, Priced]
    studies: dict[str, Study]

    @model_validator(mode="after")
    def _check(self) -> PlansConfig:
        for required in ("decouverte", "pass_memoire"):
            if required not in self.plans:
                raise ValueError(f"plan {required!r} is required")
        for code, plan in self.plans.items():
            if plan.inherits and plan.inherits not in self.plans:
                raise ValueError(f"plan {code} inherits unknown plan {plan.inherits}")
            if not plan.custom:
                if self._get(code, "responses") is None:
                    raise ValueError(f"plan {code} needs responses")
                prices = [plan.price, plan.price_once, plan.price_monthly]
                if sum(p is not None for p in prices) != 1:
                    raise ValueError(f"plan {code} needs exactly one of price, price_once, price_monthly")
                if plan.price_once is not None and (plan.duration_days is None or plan.auto_renew is not False):
                    raise ValueError(f"one time plan {code} needs duration_days and auto_renew: false (E-04)")
                if self._get(code, "exports") is None:
                    raise ValueError(f"plan {code} needs exports")
        for code in self.pioneer.plans:
            if code not in self.plans or self.plans[code].price_monthly is None:
                raise ValueError(f"pioneer plan {code!r} is not a subscription plan")
        if self.supervisor_program.grants_plan not in self.plans:
            raise ValueError("supervisor_program.grants_plan is unknown")
        return self

    def _get(self, code: str, attr: str) -> Any:
        plan = self.plans[code]
        value = getattr(plan, attr)
        if value is None and plan.inherits:
            return self._get(plan.inherits, attr)
        return value

    def features_of(self, code: str) -> frozenset[str]:
        plan = self.plans[code]
        own: set[str] = {*plan.features, *plan.extra_features}
        if plan.inherits:
            own |= self.features_of(plan.inherits)
        return frozenset(own)

    def exports_of(self, code: str) -> frozenset[str]:
        return frozenset(self._get(code, "exports") or ())

    def limit(self, code: str, attr: str) -> int | None:
        """Numeric limit, None when unlimited or not set."""
        value = self._get(code, attr)
        return None if value in (None, "unlimited") else int(value)

    def responses_limit(self, code: str) -> tuple[int | None, Literal["month", "total"]]:
        r: Responses | None = self._get(code, "responses")
        if r is None:
            return None, "month"
        return (r.per_month, "month") if r.per_month is not None else (r.total, "total")

    def payment_fee_bps(self, code: str) -> int:
        return self.plans[code].payment_fee_bps

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
