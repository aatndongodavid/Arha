"""F-LOG-02: the shared conformance suite passes in Python (and in TypeScript, see packages/logic-ts)."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import pytest

from arha.modules.logic.engine import evaluate

CASES_DIR = Path(__file__).resolve().parents[3] / "packages" / "logic-conformance" / "cases"
SCHEMAS: dict[str, Any] = json.loads((CASES_DIR / "_schemas.json").read_text(encoding="utf-8"))
CASES = [c for f in sorted(CASES_DIR.glob("[!_]*.json")) for c in json.loads(f.read_text(encoding="utf-8"))]


def test_F_LOG_02_suite_has_at_least_300_cases() -> None:
    assert len(CASES) >= 300


@pytest.mark.parametrize("case", CASES, ids=[c["name"] for c in CASES])
def test_F_LOG_02_conformance(case: dict[str, Any]) -> None:
    result = evaluate(SCHEMAS[case["base"]], case["answers"], case.get("hidden")).as_expect()
    exact = case["name"].startswith("gen_")
    for key, expected in case["expect"].items():
        if isinstance(expected, dict) and not exact:
            got = {k: result[key].get(k) for k in expected}
            assert got == expected, f"{case['name']}: {key}"
        else:
            assert result[key] == expected, f"{case['name']}: {key}"
