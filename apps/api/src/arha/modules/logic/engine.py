"""Reference logic engine (F-LOG-01..05). Mirrored by packages/logic-ts; both pass
packages/logic-conformance. The server always recomputes with this engine (rule 2).

Numbers are fixed point integers scaled by 10**6 so that Python and TypeScript produce
identical results to the franc. Final amounts use banker's rounding to the currency unit.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from datetime import date
from typing import Any

SCALE = 1_000_000
INPUT_TYPES = {
    "short_text", "long_text", "email", "phone", "url", "number", "single_choice", "multi_choice", "dropdown",
    "yes_no", "ranking", "choice_grid", "rating", "linear_scale", "nps", "date", "time", "date_range",
    "file_upload", "signature", "payment_open", "product_choice", "ticket_choice", "hidden", "consent",
}
PAYMENT_TYPES = {"payment_fixed", "payment_computed", "payment_open", "product_choice", "ticket_choice"}
CHOICE_TYPES = {"single_choice", "dropdown"}
EMAIL_RE = re.compile(r"^[^@\s]{1,64}@[^@\s]+\.[A-Za-z]{2,}$")
URL_RE = re.compile(r"^https?://[^\s/$.?#][^\s]*$", re.IGNORECASE)
E164_RE = re.compile(r"^\+[1-9]\d{7,14}$")
CM_MOBILE_RE = re.compile(r"^\+237[62]\d{8}$")
DATE_RE = re.compile(r"^\d{4}-\d{2}-\d{2}$")
TIME_RE = re.compile(r"^([01]\d|2[0-3]):[0-5]\d$")


# ------------------------------------------------------------------ fixed point arithmetic


def to_fixed(value: Any) -> int:
    """Convert a JSON number (or numeric string) to a scaled integer, rounding half to even."""
    if isinstance(value, bool) or value is None:
        return 0
    if isinstance(value, int):
        return value * SCALE
    if isinstance(value, float):
        return _parse_decimal(repr(value))
    if isinstance(value, str):
        try:
            return _parse_decimal(value.strip())
        except ValueError:
            return 0
    return 0


def _parse_decimal(text: str) -> int:
    m = re.fullmatch(r"([+-]?)(\d*)(?:\.(\d*))?(?:[eE]([+-]?\d+))?", text)
    if not m or (not m.group(2) and not m.group(3)):
        raise ValueError(text)
    sign = -1 if m.group(1) == "-" else 1
    digits = (m.group(2) or "0") + (m.group(3) or "")
    exp = int(m.group(4) or 0) - len(m.group(3) or "") + 6
    n = int(digits)
    if exp >= 0:
        return sign * n * 10**exp
    return sign * div_round_half_even(n, 10 ** (-exp))


def div_round_half_even(a: int, b: int) -> int:
    """Integer division a/b rounded half to even. b > 0."""
    if b < 0:
        a, b = -a, -b
    q, r = divmod(a, b)
    twice = 2 * r
    if twice > b or (twice == b and q % 2 == 1):
        q += 1
    return q


def fixed_mul(a: int, b: int) -> int:
    return div_round_half_even(a * b, SCALE)


def fixed_div(a: int, b: int) -> int:
    return div_round_half_even(a * SCALE, b)


def fixed_round(a: int, digits: int) -> int:
    digits = max(0, min(6, digits))
    unit = 10 ** (6 - digits)
    return div_round_half_even(a, unit) * unit


def to_currency_unit(a: int) -> int:
    return div_round_half_even(a, SCALE)


def fixed_to_json(a: int) -> int | float:
    if a % SCALE == 0:
        return a // SCALE
    sign = "-" if a < 0 else ""
    whole, frac = divmod(abs(a), SCALE)
    return float(f"{sign}{whole}.{frac:06d}")


# ------------------------------------------------------------------ helpers


@dataclass
class Num:
    v: int  # scaled


Value = Any  # Num | str | bool | list | dict | None


def is_empty(v: Any) -> bool:
    if v is None:
        return True
    if isinstance(v, str):
        return v.strip() == ""
    if isinstance(v, list | dict):
        return len(v) == 0 or (isinstance(v, dict) and all(is_empty(x) or x == 0 for x in v.values()))
    return False


def _as_num(v: Any) -> int:
    if isinstance(v, Num):
        return v.v
    if isinstance(v, bool):
        return SCALE if v else 0
    if isinstance(v, int | float | str):
        return to_fixed(v)
    if isinstance(v, list):
        return len(v) * SCALE
    return 0


def _truthy(v: Any) -> bool:
    if isinstance(v, Num):
        return v.v != 0
    return bool(v) and not is_empty(v)


def _norm(v: Any) -> Any:
    """Normalize a raw value for comparisons."""
    if isinstance(v, Num):
        return v
    if isinstance(v, bool):
        return v
    if isinstance(v, int | float):
        return Num(to_fixed(v))
    return v


def _numeric_like(v: Any) -> bool:
    if isinstance(v, Num):
        return True
    if isinstance(v, int | float) and not isinstance(v, bool):
        return True
    if isinstance(v, str):
        return re.fullmatch(r"[+-]?\d+(\.\d+)?", v.strip() or "x") is not None
    return False


def _cmp(a: Any, b: Any) -> int | None:
    """Three-way comparison. Numbers numerically, other values as strings (ISO dates sort)."""
    if a is None or b is None:
        return None
    if _numeric_like(a) and _numeric_like(b):
        x, y = _as_num(_norm(a)), _as_num(_norm(b))
        return (x > y) - (x < y)
    if isinstance(a, str) and isinstance(b, str):
        return (a > b) - (a < b)
    return None


def _eq(a: Any, b: Any) -> bool:
    if isinstance(a, list) or isinstance(b, list):
        if isinstance(a, list) and isinstance(b, list):
            return sorted(map(str, a)) == sorted(map(str, b))
        return False
    if isinstance(a, bool) or isinstance(b, bool):
        return a is b or a == b
    c = _cmp(a, b)
    if c is not None:
        return c == 0
    return bool(a == b)


# ------------------------------------------------------------------ evaluation


@dataclass
class Result:
    visible: list[str]
    required: list[str]
    variables: dict[str, Any]
    path: list[str]
    ended: bool
    next_page: dict[str, str | None]
    errors: list[dict[str, str]]
    amount: int  # currency unit, banker's rounding
    line_items: list[dict[str, Any]] = field(default_factory=list)
    clean_answers: dict[str, Any] = field(default_factory=dict)

    def as_expect(self) -> dict[str, Any]:
        return {"visible": self.visible, "required": self.required, "variables": self.variables,
                "path": self.path, "ended": self.ended, "nextPage": self.next_page, "errors": self.errors,
                "amount": self.amount}


class Evaluator:
    def __init__(self, schema: dict[str, Any]) -> None:
        self.schema = schema
        self.pages: list[dict[str, Any]] = schema.get("pages", [])
        self.blocks: dict[str, dict[str, Any]] = {}
        self.block_page: dict[str, str] = {}
        self.page_index: dict[str, int] = {}
        for i, page in enumerate(self.pages):
            self.page_index[page["id"]] = i
            for b in page.get("blocks", []):
                self.blocks[b["id"]] = b
                self.block_page[b["id"]] = page["id"]
        self.variables_def: list[dict[str, Any]] = schema.get("variables", [])
        self.rules: list[dict[str, Any]] = schema.get("rules", [])
        self.errors: list[dict[str, str]] = []

    # -- values

    def field_value(self, fid: str, answers: dict[str, Any], variables: dict[str, Any]) -> Any:
        if fid in variables:
            v = variables[fid]
            return Num(v) if isinstance(v, int) and not isinstance(v, bool) else v
        block = self.blocks.get(fid)
        raw = answers.get(fid)
        if block is None:
            return raw
        t = block["type"]
        if raw is None:
            return None
        if t in ("number", "rating", "linear_scale", "nps", "payment_open"):
            return Num(to_fixed(raw)) if _numeric_like(raw) else None
        if t == "yes_no":
            return raw if isinstance(raw, bool) else None
        return raw

    def eval_expr(self, expr: dict[str, Any], answers: dict[str, Any], variables: dict[str, Any]) -> Any:
        if "num" in expr:
            return Num(to_fixed(expr["num"]))
        if "str" in expr:
            return expr["str"]
        if "bool" in expr:
            return bool(expr["bool"])
        if "ref" in expr:
            return self.field_value(expr["ref"], answers, variables)
        op = expr.get("op")
        args = expr.get("args", [])
        if op == "if":
            cond = self.eval_expr(args[0], answers, variables) if args else False
            branch = args[1] if _truthy(cond) else (args[2] if len(args) > 2 else None)
            return self.eval_expr(branch, answers, variables) if branch is not None else Num(0)
        if op in ("and", "or"):
            vals = [_truthy(self.eval_expr(a, answers, variables)) for a in args]
            return all(vals) if op == "and" else any(vals)
        if op == "not":
            return not _truthy(self.eval_expr(args[0], answers, variables)) if args else True
        if op == "count_selected":
            v = self.eval_expr(args[0], answers, variables) if args else None
            if isinstance(v, list):
                return Num(len(v) * SCALE)
            if isinstance(v, dict):
                return Num(sum(1 for q in v.values() if _as_num(q) > 0) * SCALE)
            return Num(0 if is_empty(v) else SCALE)
        vals = [self.eval_expr(a, answers, variables) for a in args]
        if op in ("eq", "neq", "gt", "gte", "lt", "lte"):
            if len(vals) < 2:
                return False
            a, b = vals[0], vals[1]
            if op == "eq":
                return _eq(a, b)
            if op == "neq":
                return not _eq(a, b)
            c = _cmp(a, b)
            if c is None:
                return False
            return {"gt": c > 0, "gte": c >= 0, "lt": c < 0, "lte": c <= 0}[op]
        nums: list[int] = []
        for v in vals:
            if isinstance(v, dict):  # product quantities
                nums.append(sum(_as_num(q) for q in v.values()))
            else:
                nums.append(_as_num(v))
        if op == "add" or op == "sum":
            return Num(sum(nums))
        if op == "sub":
            if not nums:
                return Num(0)
            return Num(nums[0] - sum(nums[1:]))
        if op == "mul":
            acc = SCALE
            for n in nums:
                acc = fixed_mul(acc, n)
            return Num(acc if nums else 0)
        if op == "div":
            if len(nums) < 2:
                return Num(0)
            if nums[1] == 0:
                self.errors.append({"field": "_formula", "code": "division_by_zero"})
                return Num(0)
            return Num(fixed_div(nums[0], nums[1]))
        if op == "round":
            digits = to_currency_unit(nums[1]) if len(nums) > 1 else 0
            return Num(fixed_round(nums[0] if nums else 0, digits))
        if op == "min":
            return Num(min(nums)) if nums else Num(0)
        if op == "max":
            return Num(max(nums)) if nums else Num(0)
        return None

    # -- conditions

    def eval_condition(self, cond: dict[str, Any], answers: dict[str, Any], variables: dict[str, Any]) -> bool:
        if "all" in cond:
            return all(self.eval_condition(c, answers, variables) for c in cond["all"])
        if "any" in cond:
            return any(self.eval_condition(c, answers, variables) for c in cond["any"])
        value = self.field_value(cond["field"], answers, variables)
        op = cond["op"]
        expected = cond.get("value")
        if op == "empty":
            return is_empty(value)
        if op == "not_empty":
            return not is_empty(value)
        if op == "eq":
            return _eq(value, expected)
        if op == "neq":
            return not _eq(value, expected)
        if op in ("contains", "not_contains"):
            if isinstance(value, list):
                hit = any(str(x) == str(expected) for x in value)
            elif isinstance(value, dict):
                hit = _as_num(value.get(str(expected))) > 0
            elif isinstance(value, str) and isinstance(expected, str):
                hit = expected.lower() in value.lower()
            else:
                hit = False
            return hit if op == "contains" else not hit
        if op in ("in", "not_in"):
            options = expected if isinstance(expected, list) else [expected]
            if isinstance(value, list):
                hit = any(any(_eq(v, o) for o in options) for v in value)
            else:
                hit = value is not None and any(_eq(value, o) for o in options)
            return hit if op == "in" else not hit
        if op == "between":
            if not isinstance(expected, list) or len(expected) != 2:
                return False
            lo, hi = _cmp(value, expected[0]), _cmp(value, expected[1])
            return lo is not None and hi is not None and lo >= 0 and hi <= 0
        c = _cmp(value, expected)
        if c is None:
            return False
        return {"gt": c > 0, "gte": c >= 0, "lt": c < 0, "lte": c <= 0}.get(op, False)

    # -- main

    def rule_page(self, rule: dict[str, Any]) -> str | None:
        if rule.get("page"):
            return str(rule["page"])
        fields = _condition_fields(rule["when"])
        idx = [self.page_index[self.block_page[f]] for f in fields if f in self.block_page]
        return self.pages[max(idx)]["id"] if idx else (self.pages[0]["id"] if self.pages else None)

    def run(self, answers: dict[str, Any], hidden: dict[str, str] | None = None) -> Result:
        self.errors = []
        answers = dict(answers)
        for bid, b in self.blocks.items():
            if b["type"] == "hidden" and hidden is not None:
                param = b.get("param") or bid
                if param in hidden:
                    answers[bid] = str(hidden[param])[:500]

        variables: dict[str, Any] = {}
        for var in self.variables_def:
            if var.get("formula") is not None:
                variables[var["id"]] = self._store(self.eval_expr(var["formula"], answers, variables))
            else:
                init = var.get("initial")
                variables[var["id"]] = to_fixed(init) if isinstance(init, int | float) and not isinstance(
                    init, bool) else init

        shown_by_rule = {a.get("target") for r in self.rules for a in r["then"] if a["action"] == "show"}
        visible = {bid for bid in self.blocks if bid not in shown_by_rule}
        required = {bid for bid, b in self.blocks.items() if b.get("required") and b["type"] in INPUT_TYPES}
        jumps: dict[str, str | None] = {}
        ended_at: set[str] = set()

        for rule in self.rules:
            if not self.eval_condition(rule["when"], answers, variables):
                continue
            page = self.rule_page(rule)
            for act in rule["then"]:
                kind, target = act["action"], act.get("target")
                if kind == "show" and target:
                    visible.add(target)
                elif kind == "hide" and target:
                    visible.discard(target)
                elif kind == "require" and target:
                    required.add(target)
                elif kind == "unrequire" and target:
                    required.discard(target)
                elif kind == "set_variable" and target:
                    variables[target] = self._store(self.eval_expr(act.get("value") or {"num": 0}, answers,
                                                                   variables))
                elif kind == "jump_to_page" and target and page and page not in jumps:
                    jumps[page] = target
                elif kind == "end_form" and page and page not in jumps:
                    jumps[page] = None
                    ended_at.add(page)

        # Page path from the first page, following jumps; a cycle stops the walk.
        path: list[str] = []
        next_page: dict[str, str | None] = {}
        ended = False
        for i, page in enumerate(self.pages):
            pid = page["id"]
            if pid in jumps:
                target = jumps[pid]
                next_page[pid] = target if target in self.page_index else None
            else:
                next_page[pid] = self.pages[i + 1]["id"] if i + 1 < len(self.pages) else None
        current: str | None = self.pages[0]["id"] if self.pages else None
        seen: set[str] = set()
        while current is not None and current not in seen:
            seen.add(current)
            path.append(current)
            if current in ended_at:
                ended = True
                break
            current = next_page.get(current)
        on_path = set(path)

        visible = {b for b in visible if self.block_page.get(b) in on_path}
        # Visible payment blocks refresh computed values after visibility is known.
        clean: dict[str, Any] = {}
        for bid in self.blocks:
            if bid in visible and bid in answers and self.blocks[bid]["type"] in INPUT_TYPES:
                clean[bid] = answers[bid]
        required = {r for r in required if r in visible}

        self._validate(clean, visible, required)
        amount_fixed, items = self._amount(clean, visible, variables)

        visible_inputs = [bid for bid in self.blocks if bid in visible]
        return Result(
            visible=visible_inputs,
            required=[bid for bid in self.blocks if bid in required],
            variables={k: (fixed_to_json(v) if isinstance(v, int) and not isinstance(v, bool) else v)
                       for k, v in variables.items()},
            path=path, ended=ended, next_page=next_page,
            errors=self.errors, amount=max(0, to_currency_unit(amount_fixed)), line_items=items,
            clean_answers=clean,
        )

    @staticmethod
    def _store(v: Any) -> Any:
        if isinstance(v, Num):
            return v.v
        return v

    # -- validation

    def _err(self, fid: str, code: str) -> None:
        self.errors.append({"field": fid, "code": code})

    def _validate(self, answers: dict[str, Any], visible: set[str], required: set[str]) -> None:
        for bid, block in self.blocks.items():
            if bid not in visible or block["type"] not in INPUT_TYPES:
                continue
            value = answers.get(bid)
            if is_empty(value) or (block["type"] == "consent" and value is not True):
                if bid in required:
                    self._err(bid, "required")
                continue
            self._validate_value(bid, block, value)

    def _validate_value(self, bid: str, block: dict[str, Any], value: Any) -> None:
        t = block["type"]
        rules = block.get("validation") or {}
        option_ids = {o["id"] for o in block.get("options") or []}
        if t in ("short_text", "long_text", "hidden", "signature"):
            if not isinstance(value, str):
                return self._err(bid, "invalid_type")
            max_len = rules.get("maxLength", 500 if t in ("short_text", "hidden") else 10000)
            if t == "signature":
                max_len = 200_000
            if len(value) > max_len:
                return self._err(bid, "too_long")
            if len(value.strip()) < rules.get("minLength", 0):
                return self._err(bid, "too_short")
        elif t == "email":
            if not isinstance(value, str) or len(value) > 254 or not EMAIL_RE.match(value.strip()):
                return self._err(bid, "invalid_email")
        elif t == "url":
            if not isinstance(value, str) or len(value) > 2048 or not URL_RE.match(value.strip()):
                return self._err(bid, "invalid_url")
        elif t == "phone":
            if not isinstance(value, str) or not E164_RE.match(value):
                return self._err(bid, "invalid_phone")
            if value.startswith("+237") and not CM_MOBILE_RE.match(value):
                return self._err(bid, "invalid_phone")
        elif t in ("number", "rating", "linear_scale", "nps", "payment_open"):
            if not _numeric_like(value):
                return self._err(bid, "invalid_number")
            n = to_fixed(value)
            lo, hi = self._numeric_bounds(block)
            integer = rules.get("integer") or t in ("rating", "linear_scale", "nps", "payment_open")
            if integer and n % SCALE != 0:
                return self._err(bid, "invalid_number")
            if lo is not None and n < lo:
                return self._err(bid, "below_min")
            if hi is not None and n > hi:
                return self._err(bid, "above_max")
        elif t in CHOICE_TYPES:
            if not isinstance(value, str) or value not in option_ids:
                return self._err(bid, "invalid_choice")
        elif t == "multi_choice" or t == "ranking":
            if not isinstance(value, list) or any(not isinstance(v, str) or v not in option_ids for v in value):
                return self._err(bid, "invalid_choice")
            if len(set(value)) != len(value):
                return self._err(bid, "invalid_choice")
            if t == "ranking" and set(value) != option_ids:
                return self._err(bid, "invalid_choice")
            if len(value) < rules.get("minSelected", 0):
                return self._err(bid, "too_few")
            if "maxSelected" in rules and len(value) > rules["maxSelected"]:
                return self._err(bid, "too_many")
        elif t == "yes_no":
            if not isinstance(value, bool):
                return self._err(bid, "invalid_choice")
        elif t == "consent":
            if value is not True:
                return self._err(bid, "required")
        elif t == "choice_grid":
            rows = {r["id"] for r in block.get("rows") or []}
            cols = {c["id"] for c in block.get("columns") or []}
            if not isinstance(value, dict) or any(k not in rows or v not in cols for k, v in value.items()):
                return self._err(bid, "invalid_choice")
        elif t == "date":
            if not isinstance(value, str) or not _valid_date(value):
                return self._err(bid, "invalid_date")
            if rules.get("minDate") and value < rules["minDate"]:
                return self._err(bid, "below_min")
            if rules.get("maxDate") and value > rules["maxDate"]:
                return self._err(bid, "above_max")
        elif t == "time":
            if not isinstance(value, str) or not TIME_RE.match(value):
                return self._err(bid, "invalid_time")
        elif t == "date_range":
            if (not isinstance(value, dict) or not _valid_date(str(value.get("start", "")))
                    or not _valid_date(str(value.get("end", ""))) or value["start"] > value["end"]):
                return self._err(bid, "invalid_date")
        elif t == "file_upload":
            if not isinstance(value, list) or any(not isinstance(v, str) or len(v) > 200 for v in value):
                return self._err(bid, "invalid_file")
            if len(value) > rules.get("maxFiles", 1):
                return self._err(bid, "too_many")
        elif t in ("product_choice", "ticket_choice"):
            if not isinstance(value, dict):
                return self._err(bid, "invalid_choice")
            opts = {o["id"]: o for o in block.get("options") or []}
            for k, q in value.items():
                if k not in opts or isinstance(q, bool) or not isinstance(q, int) or q < 0:
                    return self._err(bid, "invalid_choice")
                if q > opts[k].get("maxQuantity", 10):
                    return self._err(bid, "too_many")
        return None

    @staticmethod
    def _numeric_bounds(block: dict[str, Any]) -> tuple[int | None, int | None]:
        t = block["type"]
        rules = block.get("validation") or {}
        if t == "nps":
            return 0, 10 * SCALE
        if t == "rating":
            scale = block.get("scale") or {}
            return SCALE, to_fixed(scale.get("max", 5))
        if t == "linear_scale":
            scale = block.get("scale") or {}
            return to_fixed(scale.get("min", 1)), to_fixed(scale.get("max", 5))
        if t == "payment_open":
            lo = block.get("minAmount", 1)
            hi = block.get("maxAmount")
            return to_fixed(lo), (to_fixed(hi) if hi is not None else to_fixed(10_000_000))
        lo = to_fixed(rules["min"]) if "min" in rules else None
        hi = to_fixed(rules["max"]) if "max" in rules else None
        return lo, hi

    # -- amount

    def _amount(self, answers: dict[str, Any], visible: set[str], variables: dict[str, Any]
                ) -> tuple[int, list[dict[str, Any]]]:
        total = 0
        items: list[dict[str, Any]] = []
        for bid, block in self.blocks.items():
            t = block["type"]
            if t not in PAYMENT_TYPES or bid not in visible:
                continue
            if t == "payment_fixed":
                amt = to_fixed(block.get("amount", 0))
                total += amt
                items.append({"block": bid, "amount": to_currency_unit(amt)})
            elif t == "payment_computed":
                v = variables.get(block.get("variable", ""))
                amt = v if isinstance(v, int) and not isinstance(v, bool) else 0
                amt = max(0, amt)
                total += amt
                items.append({"block": bid, "amount": to_currency_unit(amt)})
            elif t == "payment_open":
                v = answers.get(bid)
                if _numeric_like(v):
                    amt = max(0, to_fixed(v))
                    total += amt
                    items.append({"block": bid, "amount": to_currency_unit(amt)})
            else:
                qty = answers.get(bid)
                if not isinstance(qty, dict):
                    continue
                for opt in block.get("options") or []:
                    q = qty.get(opt["id"])
                    if isinstance(q, int) and not isinstance(q, bool) and q > 0:
                        amt = to_fixed(opt.get("price", 0)) * q
                        total += amt
                        items.append({"block": bid, "option": opt["id"], "quantity": q,
                                      "unit_price": int(opt.get("price", 0)), "amount": to_currency_unit(amt)})
        return total, items


def _valid_date(value: str) -> bool:
    if not DATE_RE.match(value):
        return False
    try:
        date.fromisoformat(value)
    except ValueError:
        return False
    return True


def _condition_fields(cond: dict[str, Any]) -> list[str]:
    if "all" in cond:
        return [f for c in cond["all"] for f in _condition_fields(c)]
    if "any" in cond:
        return [f for c in cond["any"] for f in _condition_fields(c)]
    return [cond["field"]] if "field" in cond else []


def evaluate(schema: dict[str, Any], answers: dict[str, Any], hidden: dict[str, str] | None = None) -> Result:
    return Evaluator(schema).run(answers, hidden)


__all__ = ["Result", "evaluate", "SCALE", "INPUT_TYPES", "PAYMENT_TYPES", "_condition_fields"]
