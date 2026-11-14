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


def require_export(org: Any, fmt: str) -> None:
    """Export formats come from the plan's `exports` list (config/plans.yaml, section 11)."""
    if fmt not in get_plans().exports_of(org.plan_code):
        raise AppError("export_not_in_plan", 402, params={"format": fmt}, extra={"format": fmt})
