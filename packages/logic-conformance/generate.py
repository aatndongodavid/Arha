"""Generate packages/logic-conformance/cases/*.json.

Hand written cases carry explicit expectations reasoned independently from the engine.
Generated cases come from Hypothesis (derandomized), their expectations come from the Python
reference engine and are frozen. The TypeScript engine must reproduce every case exactly.

Run: cd apps/api && uv run python ../../packages/logic-conformance/generate.py
"""

from __future__ import annotations

import json
import shutil
from pathlib import Path
from typing import Any

from hypothesis import HealthCheck, given, settings
from hypothesis import strategies as st

from arha.modules.logic.engine import evaluate

OUT = Path(__file__).parent / "cases"


def t(fr: str, en: str | None = None) -> dict[str, str]:
    return {"fr": fr, "en": en or fr}


def form(pages: list[dict[str, Any]], rules: list[dict[str, Any]] | None = None,
         variables: list[dict[str, Any]] | None = None, payments: bool = False) -> dict[str, Any]:
    return {"schemaVersion": 1, "defaultLocale": "fr", "locales": ["fr", "en"],
            "settings": {"payments": {"enabled": payments, "currency": "XAF", "feeBearer": "org",
                                      "provider": "fake"}},
            "variables": variables or [], "pages": pages, "rules": rules or []}


def opts(*ids: str, **prices: int) -> list[dict[str, Any]]:
    out = []
    for i, oid in enumerate(ids):
        o: dict[str, Any] = {"id": oid, "label": t(oid), "code": i + 1}
        if oid in prices:
            o["price"] = prices[oid]
        out.append(o)
    return out


def ref(x: str) -> dict[str, str]:
    return {"ref": x}


def num(x: float) -> dict[str, float]:
    return {"num": x}


def op(name: str, *args: dict[str, Any]) -> dict[str, Any]:
    return {"op": name, "args": list(args)}


# ------------------------------------------------------------------ base schemas

REGISTRATION = form(
    pages=[
        {"id": "p1", "blocks": [
            {"id": "h1", "type": "heading", "content": t("Inscription")},
            {"id": "q_role", "type": "single_choice", "label": t("Role"), "required": True,
             "options": opts("parent", "student", "teacher")},
            {"id": "q_age", "type": "number", "label": t("Age"), "validation": {"min": 0, "max": 120, "integer": True}},
            {"id": "q_guardian", "type": "short_text", "label": t("Tuteur")},
        ]},
        {"id": "p2", "blocks": [
            {"id": "q_children", "type": "number", "label": t("Enfants"), "validation": {"min": 1, "max": 20}},
            {"id": "q_email", "type": "email", "label": t("E-mail"), "required": True},
        ]},
        {"id": "p3", "blocks": [{"id": "q_comment", "type": "long_text", "label": t("Commentaire")}]},
    ],
    rules=[
        {"id": "r1", "when": {"all": [{"field": "q_role", "op": "eq", "value": "parent"},
                                      {"any": [{"field": "q_age", "op": "gte", "value": 18},
                                               {"field": "q_guardian", "op": "not_empty"}]}]},
         "then": [{"action": "show", "target": "q_children"}, {"action": "require", "target": "q_children"}]},
        {"id": "r2", "when": {"field": "q_role", "op": "eq", "value": "teacher"},
         "then": [{"action": "jump_to_page", "target": "p3"}]},
    ],
)

PRICING = form(
    pages=[{"id": "p1", "blocks": [
        {"id": "q_qty", "type": "number", "label": t("Quantite"), "required": True,
         "validation": {"min": 1, "max": 1000, "integer": True}},
        {"id": "show_total", "type": "computed_display", "variable": "total"},
        {"id": "pay", "type": "payment_computed", "label": t("Paiement"), "variable": "total"},
    ]}],
    variables=[{"id": "total", "type": "number", "formula": op(
        "if", op("gte", ref("q_qty"), num(10)), op("mul", ref("q_qty"), num(4500)),
        op("mul", ref("q_qty"), num(5000)))}],
    payments=True,
)

PRODUCTS = form(
    pages=[{"id": "p1", "blocks": [
        {"id": "q_member", "type": "yes_no", "label": t("Membre"), "required": True},
        {"id": "q_items", "type": "product_choice", "label": t("Articles"),
         "options": opts("tshirt", "cap", tshirt=7500, cap=3000)},
        {"id": "fee", "type": "payment_fixed", "label": t("Frais"), "amount": 2000},
    ]}],
    rules=[{"id": "r1", "when": {"field": "q_member", "op": "eq", "value": True},
            "then": [{"action": "hide", "target": "fee"}]}],
    payments=True,
)

ENDING = form(
    pages=[
        {"id": "p1", "blocks": [{"id": "q_ok", "type": "yes_no", "label": t("Accord"), "required": True}]},
        {"id": "p2", "blocks": [{"id": "q_name", "type": "short_text", "label": t("Nom"), "required": True}]},
    ],
    rules=[{"id": "r1", "when": {"field": "q_ok", "op": "eq", "value": False},
            "then": [{"action": "end_form"}]}],
)

MATH = form(
    pages=[{"id": "p1", "blocks": [
        {"id": "q_a", "type": "number", "label": t("A")},
        {"id": "q_b", "type": "number", "label": t("B")},
        {"id": "q_tags", "type": "multi_choice", "label": t("Tags"), "options": opts("x", "y", "z"),
         "validation": {"maxSelected": 2}},
        {"id": "pay", "type": "payment_computed", "label": t("Paiement"), "variable": "price"},
    ]}],
    variables=[
        {"id": "ratio", "type": "number", "formula": op("div", ref("q_a"), ref("q_b"))},
        {"id": "rounded", "type": "number", "formula": op("round", ref("ratio"), num(0))},
        {"id": "count", "type": "number", "formula": op("count_selected", ref("q_tags"))},
        {"id": "price", "type": "number", "formula": op("add", ref("q_a"), op("mul", ref("count"), num(0.5)))},
        {"id": "big", "type": "number", "formula": op("max", ref("q_a"), ref("q_b"), num(3))},
        {"id": "small", "type": "number", "formula": op("min", ref("q_a"), ref("q_b"))},
        {"id": "diff", "type": "number", "formula": op("sub", ref("q_a"), ref("q_b"), num(1))},
        {"id": "both", "type": "boolean", "formula": op("and", op("gt", ref("q_a"), num(0)),
                                                        op("not", op("eq", ref("q_b"), num(0))))},
    ],
    payments=True,
)

OPERATORS = form(
    pages=[{"id": "p1", "blocks": [
        {"id": "q_txt", "type": "short_text", "label": t("Texte")},
        {"id": "q_n", "type": "number", "label": t("N")},
        {"id": "q_multi", "type": "multi_choice", "label": t("Multi"), "options": opts("a", "b", "c")},
        {"id": "q_date", "type": "date", "label": t("Date")},
        {"id": "t_contains", "type": "short_text", "label": t("contains")},
        {"id": "t_not_contains", "type": "short_text", "label": t("not_contains")},
        {"id": "t_between", "type": "short_text", "label": t("between")},
        {"id": "t_in", "type": "short_text", "label": t("in")},
        {"id": "t_not_in", "type": "short_text", "label": t("not_in")},
        {"id": "t_lt", "type": "short_text", "label": t("lt")},
        {"id": "t_lte", "type": "short_text", "label": t("lte")},
        {"id": "t_gt", "type": "short_text", "label": t("gt")},
        {"id": "t_neq", "type": "short_text", "label": t("neq")},
        {"id": "t_empty", "type": "short_text", "label": t("empty")},
        {"id": "t_date", "type": "short_text", "label": t("date")},
        {"id": "t_multi", "type": "short_text", "label": t("multi")},
    ]}],
    rules=[
        {"id": "r1", "when": {"field": "q_txt", "op": "contains", "value": "arha"},
         "then": [{"action": "show", "target": "t_contains"}]},
        {"id": "r2", "when": {"field": "q_txt", "op": "not_contains", "value": "arha"},
         "then": [{"action": "show", "target": "t_not_contains"}]},
        {"id": "r3", "when": {"field": "q_n", "op": "between", "value": [10, 20]},
         "then": [{"action": "show", "target": "t_between"}]},
        {"id": "r4", "when": {"field": "q_n", "op": "in", "value": [1, 2, 3]},
         "then": [{"action": "show", "target": "t_in"}]},
        {"id": "r5", "when": {"field": "q_n", "op": "not_in", "value": [1, 2, 3]},
         "then": [{"action": "show", "target": "t_not_in"}]},
        {"id": "r6", "when": {"field": "q_n", "op": "lt", "value": 5},
         "then": [{"action": "show", "target": "t_lt"}]},
        {"id": "r7", "when": {"field": "q_n", "op": "lte", "value": 5},
         "then": [{"action": "show", "target": "t_lte"}]},
        {"id": "r8", "when": {"field": "q_n", "op": "gt", "value": 5},
         "then": [{"action": "show", "target": "t_gt"}]},
        {"id": "r9", "when": {"field": "q_txt", "op": "neq", "value": "x"},
         "then": [{"action": "show", "target": "t_neq"}]},
        {"id": "r10", "when": {"field": "q_txt", "op": "empty"},
         "then": [{"action": "show", "target": "t_empty"}]},
        {"id": "r11", "when": {"field": "q_date", "op": "gte", "value": "2027-03-02"},
         "then": [{"action": "show", "target": "t_date"}]},
        {"id": "r12", "when": {"field": "q_multi", "op": "contains", "value": "b"},
         "then": [{"action": "show", "target": "t_multi"}, {"action": "require", "target": "t_multi"}]},
    ],
)

SETVAR = form(
    pages=[{"id": "p1", "blocks": [
        {"id": "q_type", "type": "dropdown", "label": t("Type"), "options": opts("std", "vip")},
        {"id": "q_n", "type": "number", "label": t("N"), "validation": {"integer": True, "min": 0}},
        {"id": "pay", "type": "payment_computed", "label": t("Paiement"), "variable": "price"},
    ]}],
    variables=[{"id": "price", "type": "number", "initial": 10000}],
    rules=[{"id": "r1", "when": {"field": "q_type", "op": "eq", "value": "vip"},
            "then": [{"action": "set_variable", "target": "price",
                      "value": op("add", ref("price"), op("mul", ref("q_n"), num(2500.5)))}]}],
    payments=True,
)

VALIDATION = form(
    pages=[{"id": "p1", "blocks": [
        {"id": "q_email", "type": "email", "label": t("E-mail")},
        {"id": "q_phone", "type": "phone", "label": t("Telephone")},
        {"id": "q_url", "type": "url", "label": t("Site")},
        {"id": "q_rating", "type": "rating", "label": t("Note"), "scale": {"max": 5}},
        {"id": "q_nps", "type": "nps", "label": t("NPS")},
        {"id": "q_scale", "type": "linear_scale", "label": t("Echelle"), "scale": {"min": 1, "max": 7}},
        {"id": "q_date", "type": "date", "label": t("Date"), "validation": {"minDate": "2026-01-01"}},
        {"id": "q_time", "type": "time", "label": t("Heure")},
        {"id": "q_range", "type": "date_range", "label": t("Periode")},
        {"id": "q_grid", "type": "choice_grid", "label": t("Grille"), "rows": opts("r1", "r2"),
         "columns": opts("c1", "c2")},
        {"id": "q_rank", "type": "ranking", "label": t("Classement"), "options": opts("a", "b")},
        {"id": "q_short", "type": "short_text", "label": t("Court"), "validation": {"minLength": 3, "maxLength": 10}},
        {"id": "q_consent", "type": "consent", "label": t("Consentement"), "required": True},
        {"id": "q_open", "type": "payment_open", "label": t("Don"), "minAmount": 500, "maxAmount": 100000},
    ]}],
    payments=True,
)

BASES = {"registration": REGISTRATION, "pricing": PRICING, "products": PRODUCTS, "ending": ENDING, "math": MATH,
         "operators": OPERATORS, "setvar": SETVAR, "validation": VALIDATION}


# ------------------------------------------------------------------ hand written cases (explicit expectations)

HAND: list[tuple[str, str, dict[str, Any], dict[str, Any], dict[str, str] | None]] = [
    ("nested_any_all_show_require", "registration", {"q_role": "parent", "q_age": 17, "q_guardian": "Mme X"},
     {"visible": ["h1", "q_role", "q_age", "q_guardian", "q_children", "q_email", "q_comment"],
      "required": ["q_role", "q_children", "q_email"], "path": ["p1", "p2", "p3"]}, None),
    ("nested_condition_false_hides", "registration", {"q_role": "parent", "q_age": 17},
     {"visible": ["h1", "q_role", "q_age", "q_guardian", "q_email", "q_comment"],
      "required": ["q_role", "q_email"]}, None),
    ("nested_adult_parent", "registration", {"q_role": "parent", "q_age": 18, "q_children": 2, "q_email": "a@b.cm"},
     {"errors": [], "required": ["q_role", "q_children", "q_email"]}, None),
    ("required_errors", "registration", {}, {"errors": [{"field": "q_role", "code": "required"},
                                                         {"field": "q_email", "code": "required"}]}, None),
    ("teacher_jumps_to_p3", "registration", {"q_role": "teacher"},
     {"path": ["p1", "p3"], "visible": ["h1", "q_role", "q_age", "q_guardian", "q_comment"],
      "required": ["q_role"], "errors": [], "nextPage": {"p1": "p3", "p2": "p3", "p3": None}}, None),
    ("invalid_choice", "registration", {"q_role": "admin", "q_email": "x@y.cm"},
     {"errors": [{"field": "q_role", "code": "invalid_choice"}]}, None),
    ("age_not_integer", "registration", {"q_role": "student", "q_age": 17.5, "q_email": "x@y.cm"},
     {"errors": [{"field": "q_age", "code": "invalid_number"}]}, None),
    ("age_above_max", "registration", {"q_role": "student", "q_age": 121, "q_email": "x@y.cm"},
     {"errors": [{"field": "q_age", "code": "above_max"}]}, None),
    ("pricing_under_threshold", "pricing", {"q_qty": 9}, {"variables": {"total": 45000}, "amount": 45000,
                                                          "errors": []}, None),
    ("pricing_threshold", "pricing", {"q_qty": 10}, {"variables": {"total": 45000}, "amount": 45000}, None),
    ("pricing_over_threshold", "pricing", {"q_qty": 11}, {"variables": {"total": 49500}, "amount": 49500}, None),
    ("pricing_string_number", "pricing", {"q_qty": "3"}, {"amount": 15000, "errors": []}, None),
    ("pricing_missing_qty", "pricing", {}, {"amount": 0, "errors": [{"field": "q_qty", "code": "required"}]}, None),
    ("products_non_member", "products", {"q_member": False, "q_items": {"tshirt": 2, "cap": 1}},
     {"amount": 20000, "visible": ["q_member", "q_items", "fee"]}, None),
    ("products_member_no_fee", "products", {"q_member": True, "q_items": {"tshirt": 1}},
     {"amount": 7500, "visible": ["q_member", "q_items"]}, None),
    ("products_unknown_option", "products", {"q_member": True, "q_items": {"hat": 1}},
     {"errors": [{"field": "q_items", "code": "invalid_choice"}], "amount": 0}, None),
    ("products_negative_qty", "products", {"q_member": True, "q_items": {"cap": -1}},
     {"errors": [{"field": "q_items", "code": "invalid_choice"}], "amount": 0}, None),
    ("ending_stops_form", "ending", {"q_ok": False}, {"path": ["p1"], "ended": True, "errors": [],
                                                       "visible": ["q_ok"]}, None),
    ("ending_continues", "ending", {"q_ok": True}, {"path": ["p1", "p2"], "ended": False,
                                                    "errors": [{"field": "q_name", "code": "required"}]}, None),
    ("math_division", "math", {"q_a": 10, "q_b": 4}, {"variables": {"ratio": 2.5, "rounded": 2}}, None),
    ("math_bankers_round_odd", "math", {"q_a": 7, "q_b": 2}, {"variables": {"ratio": 3.5, "rounded": 4}}, None),
    ("math_division_by_zero", "math", {"q_a": 10, "q_b": 0},
     {"variables": {"ratio": 0, "both": False}, "errors": [{"field": "_formula", "code": "division_by_zero"}]}, None),
    ("math_decimal_exactness", "math", {"q_a": 0.1, "q_b": 0.2}, {"variables": {"ratio": 0.5, "big": 3,
                                                                                 "small": 0.1, "diff": -1.1}}, None),
    ("math_count_and_half_even_amount", "math", {"q_a": 1234, "q_b": 1, "q_tags": ["x"]},
     {"variables": {"count": 1, "price": 1234.5}, "amount": 1234}, None),
    ("math_half_even_up", "math", {"q_a": 1235, "q_b": 1, "q_tags": ["x"]},
     {"variables": {"price": 1235.5}, "amount": 1236}, None),
    ("math_too_many_tags", "math", {"q_a": 1, "q_b": 1, "q_tags": ["x", "y", "z"]},
     {"errors": [{"field": "q_tags", "code": "too_many"}]}, None),
    ("op_contains_case_insensitive", "operators", {"q_txt": "Bienvenue sur ARHA"},
     {"visible": ["q_txt", "q_n", "q_multi", "q_date", "t_contains", "t_not_in", "t_neq"]}, None),
    ("op_between_inclusive", "operators", {"q_txt": "x", "q_n": 20},
     {"visible": ["q_txt", "q_n", "q_multi", "q_date", "t_not_contains", "t_between", "t_not_in", "t_gt"]}, None),
    ("op_in_list", "operators", {"q_n": 2},
     {"visible": ["q_txt", "q_n", "q_multi", "q_date", "t_not_contains", "t_in", "t_lt", "t_lte", "t_neq",
                  "t_empty"]}, None),
    ("op_lte_boundary", "operators", {"q_n": 5, "q_txt": "x"},
     {"visible": ["q_txt", "q_n", "q_multi", "q_date", "t_not_contains", "t_not_in", "t_lte"]}, None),
    ("op_date_and_multi", "operators", {"q_txt": "x", "q_date": "2027-03-02", "q_multi": ["b", "c"]},
     {"visible": ["q_txt", "q_n", "q_multi", "q_date", "t_not_contains", "t_not_in", "t_date", "t_multi"],
      "required": ["t_multi"], "errors": [{"field": "t_multi", "code": "required"}]}, None),
    ("setvar_vip", "setvar", {"q_type": "vip", "q_n": 2}, {"variables": {"price": 15001}, "amount": 15001}, None),
    ("setvar_std", "setvar", {"q_type": "std", "q_n": 2}, {"variables": {"price": 10000}, "amount": 10000}, None),
    ("validation_all_valid", "validation", {
        "q_email": "awa@exemple.cm", "q_phone": "+237690000000", "q_url": "https://arha.africa", "q_rating": 5,
        "q_nps": 0, "q_scale": 7, "q_date": "2026-12-01", "q_time": "08:30",
        "q_range": {"start": "2027-01-01", "end": "2027-01-31"}, "q_grid": {"r1": "c1", "r2": "c2"},
        "q_rank": ["b", "a"], "q_short": "abcd", "q_consent": True, "q_open": 500},
     {"errors": [], "amount": 500}, None),
    ("validation_all_invalid", "validation", {
        "q_email": "awa@", "q_phone": "+23769", "q_url": "ftp://x", "q_rating": 6, "q_nps": 11, "q_scale": 0,
        "q_date": "2025-12-31", "q_time": "25:00", "q_range": {"start": "2027-02-01", "end": "2027-01-01"},
        "q_grid": {"r1": "c9"}, "q_rank": ["a"], "q_short": "ab", "q_consent": False, "q_open": 499},
     {"errors": [{"field": "q_email", "code": "invalid_email"}, {"field": "q_phone", "code": "invalid_phone"},
                 {"field": "q_url", "code": "invalid_url"}, {"field": "q_rating", "code": "above_max"},
                 {"field": "q_nps", "code": "above_max"}, {"field": "q_scale", "code": "below_min"},
                 {"field": "q_date", "code": "below_min"}, {"field": "q_time", "code": "invalid_time"},
                 {"field": "q_range", "code": "invalid_date"}, {"field": "q_grid", "code": "invalid_choice"},
                 {"field": "q_rank", "code": "invalid_choice"}, {"field": "q_short", "code": "too_short"},
                 {"field": "q_consent", "code": "required"}, {"field": "q_open", "code": "below_min"}],
      "amount": 499}, None),
    ("validation_cm_landline_ok", "validation", {"q_phone": "+237233000000", "q_consent": True}, {"errors": []}, None),
    ("validation_foreign_phone", "validation", {"q_phone": "+33612345678", "q_consent": True}, {"errors": []}, None),
    ("validation_bad_date", "validation", {"q_date": "2026-02-30", "q_consent": True},
     {"errors": [{"field": "q_date", "code": "invalid_date"}]}, None),
]

HIDDEN_FORM = form(pages=[{"id": "p1", "blocks": [
    {"id": "src", "type": "hidden", "param": "source"},
    {"id": "q_x", "type": "short_text", "label": t("X")},
    {"id": "t_wa", "type": "short_text", "label": t("WhatsApp")},
]}], rules=[{"id": "r1", "when": {"field": "src", "op": "eq", "value": "whatsapp"},
             "then": [{"action": "show", "target": "t_wa"}]}])
BASES["hidden"] = HIDDEN_FORM
HAND.append(("hidden_param_prefill", "hidden", {}, {"visible": ["src", "q_x", "t_wa"], "errors": []},
             {"source": "whatsapp"}))
HAND.append(("hidden_param_overrides_answer", "hidden", {"src": "facebook"}, {"visible": ["src", "q_x", "t_wa"]},
             {"source": "whatsapp"}))
HAND.append(("hidden_param_absent", "hidden", {}, {"visible": ["src", "q_x"]}, {}))


# ------------------------------------------------------------------ generated cases

SCALARS = st.one_of(st.none(), st.booleans(), st.integers(-5, 30), st.sampled_from([0.1, 0.5, 2.5, 9.99, 1e3, -0.5]),
                    st.sampled_from(["", " ", "3", "10", "arha", "x", "2027-03-02", "2026-01-01", "a@b.cm"]))


def answers_for(schema: dict[str, Any]) -> st.SearchStrategy[dict[str, Any]]:
    fields: dict[str, st.SearchStrategy[Any]] = {}
    for page in schema["pages"]:
        for b in page["blocks"]:
            ids = [o["id"] for o in b.get("options") or []]
            tp = b["type"]
            if tp in ("single_choice", "dropdown"):
                fields[b["id"]] = st.one_of(st.sampled_from(ids + ["zzz"]), SCALARS)
            elif tp in ("multi_choice", "ranking"):
                fields[b["id"]] = st.one_of(st.lists(st.sampled_from(ids), max_size=4), SCALARS)
            elif tp in ("product_choice", "ticket_choice"):
                fields[b["id"]] = st.one_of(st.dictionaries(st.sampled_from(ids), st.integers(-1, 12), max_size=3),
                                            SCALARS)
            elif tp == "yes_no":
                fields[b["id"]] = st.one_of(st.booleans(), SCALARS)
            elif tp in ("heading", "computed_display", "payment_fixed", "payment_computed"):
                continue
            else:
                fields[b["id"]] = SCALARS
    return st.fixed_dictionaries({}, optional=fields)


def generate() -> list[dict[str, Any]]:
    cases: list[dict[str, Any]] = []
    for name, base, answers, expect, hidden in HAND:
        case = {"name": name, "base": base, "answers": answers, "expect": expect}
        if hidden is not None:
            case["hidden"] = hidden
        cases.append(case)

    per_base = {"registration": 45, "pricing": 30, "products": 35, "ending": 20, "math": 45, "operators": 45,
                "setvar": 25, "validation": 30, "hidden": 10}
    for base, count in per_base.items():
        collected: list[dict[str, Any]] = []
        seen: set[str] = set()

        def make_collector(seen_keys: set[str], out: list[dict[str, Any]], schema: dict[str, Any]) -> Any:
            @settings(max_examples=count * 4, derandomize=True, database=None,
                      suppress_health_check=list(HealthCheck))
            @given(answers_for(schema))
            def collect(answers: dict[str, Any]) -> None:
                key = json.dumps(answers, sort_keys=True)
                if key not in seen_keys:
                    seen_keys.add(key)
                    out.append(answers)
            return collect

        make_collector(seen, collected, BASES[base])()
        for i, answers in enumerate(collected[:count]):
            result = evaluate(BASES[base], answers).as_expect()
            cases.append({"name": f"gen_{base}_{i:03d}", "base": base, "answers": answers, "expect": result})
    return cases


def main() -> None:
    if OUT.exists():
        shutil.rmtree(OUT)
    OUT.mkdir(parents=True)
    (OUT / "_schemas.json").write_text(json.dumps(BASES, indent=1, ensure_ascii=False), encoding="utf-8")
    cases = generate()
    by_base: dict[str, list[dict[str, Any]]] = {}
    for c in cases:
        by_base.setdefault(c["base"], []).append(c)
    for base, items in by_base.items():
        (OUT / f"{base}.json").write_text(json.dumps(items, indent=1, ensure_ascii=False), encoding="utf-8")
    print(f"{len(cases)} cases written")


if __name__ == "__main__":
    main()
