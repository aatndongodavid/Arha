"""Publication-time static analysis (F-LOG-03, master prompt section 8).

Errors block publication. Warnings are shown without blocking.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from arha.modules.logic.engine import INPUT_TYPES, PAYMENT_TYPES, _condition_fields

EXPR_OPS = {"add", "sub", "mul", "div", "round", "min", "max", "sum", "if", "eq", "neq", "gt", "gte", "lt", "lte",
            "and", "or", "not", "count_selected"}


@dataclass(frozen=True)
class Issue:
    severity: str  # "error" | "warning"
    code: str
    target: str | None = None
    detail: str | None = None

    def as_dict(self) -> dict[str, str | None]:
        return {"severity": self.severity, "code": self.code, "target": self.target, "detail": self.detail}


def _expr_refs(expr: Any, issues: list[Issue], where: str) -> list[str]:
    if not isinstance(expr, dict):
        issues.append(Issue("error", "formula_invalid", where))
        return []
    if "ref" in expr:
        return [expr["ref"]]
    if any(k in expr for k in ("num", "str", "bool")):
        return []
    op = expr.get("op")
    if op not in EXPR_OPS:
        issues.append(Issue("error", "formula_invalid", where, f"unknown operator {op}"))
        return []
    args = expr.get("args", [])
    if op in ("div", "sub", "eq", "neq", "gt", "gte", "lt", "lte") and len(args) < 2:
        issues.append(Issue("error", "formula_invalid", where, f"{op} needs two arguments"))
    if op == "if" and len(args) < 2:
        issues.append(Issue("error", "formula_invalid", where, "if needs a condition and a value"))
    return [r for a in args for r in _expr_refs(a, issues, where)]


def analyze(schema: dict[str, Any]) -> list[Issue]:
    issues: list[Issue] = []
    pages = schema.get("pages", [])
    page_ids = [p["id"] for p in pages]
    page_index = {pid: i for i, pid in enumerate(page_ids)}
    blocks: dict[str, dict[str, Any]] = {}
    block_page: dict[str, str] = {}
    for p in pages:
        for b in p.get("blocks", []):
            if b["id"] in blocks:
                issues.append(Issue("error", "duplicate_id", b["id"]))
            blocks[b["id"]] = b
            block_page[b["id"]] = p["id"]
    if len(set(page_ids)) != len(page_ids):
        issues.append(Issue("error", "duplicate_id", "pages"))
    variables = {v["id"]: v for v in schema.get("variables", [])}
    for vid in variables:
        if vid in blocks:
            issues.append(Issue("error", "duplicate_id", vid))
    known = set(blocks) | set(variables)

    # Variables: refs must exist and must not reference later variables (evaluation order).
    order = list(variables)
    for i, (vid, var) in enumerate(variables.items()):
        if var.get("formula") is None:
            continue
        for ref in _expr_refs(var["formula"], issues, vid):
            if ref not in known:
                issues.append(Issue("error", "unknown_reference", vid, ref))
            elif ref in variables and order.index(ref) >= i:
                issues.append(Issue("error", "formula_cycle", vid, ref))

    shown_targets: dict[str, list[dict[str, Any]]] = {}
    for rule in schema.get("rules", []):
        rid = rule.get("id")
        for f in _condition_fields(rule.get("when", {})):
            if f not in known:
                issues.append(Issue("error", "unknown_reference", rid, f))
        if rule.get("page") and rule["page"] not in page_index:
            issues.append(Issue("error", "unknown_reference", rid, rule["page"]))
        for act in rule.get("then", []):
            kind, target = act.get("action"), act.get("target")
            if kind in ("show", "hide", "require", "unrequire"):
                if target not in blocks:
                    issues.append(Issue("error", "unknown_reference", rid, target))
                if kind == "show" and target:
                    shown_targets.setdefault(target, []).append(rule)
            elif kind == "jump_to_page":
                if target not in page_index:
                    issues.append(Issue("error", "unknown_reference", rid, target))
            elif kind == "set_variable":
                if target not in variables:
                    issues.append(Issue("error", "unknown_reference", rid, target))
                for ref in _expr_refs(act.get("value") or {"num": 0}, issues, rid or ""):
                    if ref not in known:
                        issues.append(Issue("error", "unknown_reference", rid, ref))

    # Jump loops: a jump back to the same or an earlier page creates a cycle (F-LOG-03).
    for rule in schema.get("rules", []):
        for act in rule.get("then", []):
            if act.get("action") != "jump_to_page" or act.get("target") not in page_index:
                continue
            fields = _condition_fields(rule.get("when", {}))
            src = rule.get("page") or (max((block_page[f] for f in fields if f in block_page),
                                           key=lambda p: page_index[p], default=page_ids[0] if page_ids else None))
            if src is not None and page_index[act["target"]] <= page_index[src]:
                issues.append(Issue("error", "jump_loop", rule.get("id"), f"{src}->{act['target']}"))

    # Unreachable fields: shown only by rules whose condition depends on the field itself.
    for target, rules in shown_targets.items():
        if all(target in _condition_fields(r.get("when", {})) for r in rules):
            issues.append(Issue("error", "unreachable_field", target))

    # Unreachable pages: no path reaches them when every jump fires in the most permissive way.
    reachable = {page_ids[0]} if page_ids else set()
    jumps_from: dict[str, set[str]] = {}
    for rule in schema.get("rules", []):
        for act in rule.get("then", []):
            if act.get("action") == "jump_to_page" and act.get("target") in page_index:
                fields = _condition_fields(rule.get("when", {}))
                src = rule.get("page") or max((block_page[f] for f in fields if f in block_page),
                                              key=lambda p: page_index[p], default=page_ids[0])
                jumps_from.setdefault(src, set()).add(act["target"])
    frontier = list(reachable)
    while frontier:
        pid = frontier.pop()
        nxt = set(jumps_from.get(pid, set()))
        i = page_index[pid]
        if i + 1 < len(page_ids):
            nxt.add(page_ids[i + 1])
        for n in nxt - reachable:
            reachable.add(n)
            frontier.append(n)
    for pid in page_ids:
        if pid not in reachable:
            issues.append(Issue("warning", "unreachable_page", pid))

    # Block level checks.
    locales = schema.get("locales", ["fr"])
    for bid, b in blocks.items():
        t = b["type"]
        if t in INPUT_TYPES and t != "hidden":
            label = b.get("label") or {}
            for loc in locales:
                if not (label.get(loc) or "").strip():
                    issues.append(Issue("warning", "missing_translation", bid, loc))
        with_options = ("single_choice", "multi_choice", "dropdown", "ranking", "product_choice", "ticket_choice")
        if t in with_options and not b.get("options"):
            issues.append(Issue("error", "options_required", bid))
        if t in ("payment_computed", "computed_display") and b.get("variable") not in variables:
            issues.append(Issue("error", "unknown_reference", bid, b.get("variable")))
        if t == "payment_fixed" and not b.get("amount"):
            issues.append(Issue("error", "amount_required", bid))
        if t == "choice_grid" and (not b.get("rows") or not b.get("columns")):
            issues.append(Issue("error", "options_required", bid))

    from arha.modules.logic.variables import check as check_variables

    for v in check_variables(schema):
        issues.append(Issue("error", v.code, v.target, v.detail))

    has_payment = any(b["type"] in PAYMENT_TYPES for b in blocks.values())
    payments = (schema.get("settings") or {}).get("payments") or {}
    if has_payment and not payments.get("enabled"):
        issues.append(Issue("error", "payments_disabled", None))
    return issues


def has_errors(issues: list[Issue]) -> bool:
    return any(i.severity == "error" for i in issues)
