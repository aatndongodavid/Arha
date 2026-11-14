"""Feature gating by plan (master prompt section 11). Values come from config/plans.yaml only."""

from __future__ import annotations

from typing import Any

from arha.core.errors import AppError
from arha.core.plans import get_plans


def org_features(org: Any) -> frozenset[str]:
    return get_plans().features_of(org.plan_code)


def has_feature(org: Any, feature: str) -> bool:
    return feature in org_features(org)


def require_feature(org: Any, feature: str) -> None:
    if not has_feature(org, feature):
        raise AppError("feature_not_in_plan", 402, params={"feature": feature}, extra={"feature": feature})


def plan_limit(org: Any, attr: str) -> int | None:
    return get_plans().limit(org.plan_code, attr)
