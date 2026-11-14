"""Variable names and choice codes (F-EDI-12, section 7 of master prompt v1.2).

Names are generated once from the question label, then never changed by the server: a creator may edit them.
They are unique ignoring case (SPSS ignores case), at most 32 characters, start with a letter, use only
letters, digits and underscores, and avoid the reserved words of SPSS, Stata and R. Choice codes are stable:
a new choice takes the largest code plus one, an existing code is never renumbered.
"""

from __future__ import annotations

import re
import unicodedata
from collections.abc import Iterator
from dataclasses import dataclass
from typing import Any

VAR_RE = re.compile(r"^[A-Za-z][A-Za-z0-9_]{0,31}$")
RESERVED = frozenset(w.lower() for w in (
    # SPSS
    "ALL", "AND", "BY", "EQ", "GE", "GT", "LE", "LT", "NE", "NOT", "OR", "TO", "WITH",
    # Stata
    "_all", "_b", "byte", "_coef", "_cons", "double", "float", "if", "in", "int", "long", "_n", "_pi", "_pred",
    "_rc", "_skip", "str", "strL", "using",
    # R
    "else", "repeat", "while", "function", "for", "next", "break", "TRUE", "FALSE", "NULL", "Inf", "NaN", "NA",
    "NA_integer_", "NA_real_", "NA_character_", "NA_complex_",
))
# Blocks that produce no variable.
NO_VARIABLE = frozenset({"heading", "rich_text", "image", "divider", "computed_display", "payment_fixed",
                         "payment_computed"})
WITH_CODES = ("options", "columns")


def is_variable(block: dict[str, Any]) -> bool:
    return block.get("type") not in NO_VARIABLE


def slug(text: str, limit: int = 26) -> str:
    plain = "".join(c for c in unicodedata.normalize("NFKD", text) if not unicodedata.combining(c))
    words = re.findall(r"[A-Za-z0-9]+", plain.lower())
    name = "_".join(words)[:limit].strip("_")
    if not name or not name[0].isalpha():
        name = f"v_{name}".strip("_")
    return name


def _label(block: dict[str, Any]) -> str:
    label = block.get("label") or {}
    return str(label.get("fr") or label.get("en") or block.get("id") or "v")


def iter_blocks(schema: dict[str, Any]) -> Iterator[dict[str, Any]]:
    for page in schema.get("pages", []):
        yield from page.get("blocks", [])


def expansions(block: dict[str, Any]) -> list[str]:
    """Names actually written in statistical files for one block (section 8 bis, point 1)."""
    name = block.get("varName") or block["id"]
    t = block["type"]
    if t in ("multi_choice",):
        return [f"{name}_{o.get('code')}" for o in block.get("options") or []]
    if t in ("likert_matrix", "choice_grid"):
        return [f"{name}_{i + 1}" for i, _ in enumerate(block.get("rows") or [])]
    if t in ("product_choice", "ticket_choice"):
        return [f"{name}_{o.get('code')}" for o in block.get("options") or []]
    if t == "geopoint":
        return [f"{name}_lat", f"{name}_lon", f"{name}_acc"]
    if t == "date_range":
        return [f"{name}_start", f"{name}_end"]
    return [name]


def normalize(schema: dict[str, Any]) -> dict[str, Any]:
    """Fill missing variable names and choice codes in place. Existing values are never changed."""
    blocks = [b for b in iter_blocks(schema) if is_variable(b)]
    taken = {str(b["varName"]).lower() for b in blocks if b.get("varName")}
    for b in blocks:
        for key in WITH_CODES:
            items = b.get(key) or []
            if not items:
                continue
            codes = [o["code"] for o in items if isinstance(o.get("code"), int)]
            nxt = max(codes, default=0) + 1
            for o in items:
                if not isinstance(o.get("code"), int):
                    o["code"] = nxt
                    nxt += 1
        if b.get("varName"):
            continue
        base = slug(_label(b))
        if base.lower() in RESERVED:
            base = f"{base}_v"
        name, i = base, 2
        while name.lower() in taken:
            name = f"{base[:28]}_{i}"
            i += 1
        b["varName"] = name
        taken.add(name.lower())
    return schema


@dataclass(frozen=True)
class VarIssue:
    code: str
    target: str
    detail: str | None = None


def check(schema: dict[str, Any]) -> list[VarIssue]:
    """Publication checks: portable names, no collision (expansions included), coherent codes."""
    issues: list[VarIssue] = []
    seen: dict[str, str] = {}
    for b in iter_blocks(schema):
        if not is_variable(b):
            continue
        bid = b["id"]
        name = b.get("varName")
        if not name or not VAR_RE.match(name) or name.lower() in RESERVED:
            issues.append(VarIssue("varname_invalid", bid, name))
            continue
        for expanded in expansions(b):
            key = expanded.lower()
            if key in seen and seen[key] != bid:
                issues.append(VarIssue("varname_duplicate", bid, expanded))
                break
            seen[key] = bid
            if len(expanded) > 32:
                issues.append(VarIssue("varname_too_long", bid, expanded))
                break
        for key in WITH_CODES:
            codes = [o.get("code") for o in b.get(key) or []]
            if codes and (None in codes or len(set(codes)) != len(codes)):
                issues.append(VarIssue("option_code_duplicate", bid))
        missing = [m.get("code") for m in b.get("missingCodes") or []]
        choice_codes = {o.get("code") for k in WITH_CODES for o in b.get(k) or []}
        if len(set(missing)) != len(missing) or choice_codes & set(missing):
            issues.append(VarIssue("missing_code_conflict", bid))
    return issues
