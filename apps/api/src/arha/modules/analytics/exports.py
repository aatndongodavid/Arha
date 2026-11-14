"""Exports CSV, Excel, SPSS (.sav) and Stata (.dta) with a variable dictionary (F-REP-04).

Variable and value labels are kept in SPSS and Stata (verified by reading files back with pyreadstat).
"""

from __future__ import annotations

import io
import re
import tempfile
from pathlib import Path
from typing import Any

import polars as pl
import pyreadstat
import xlsxwriter

from arha.core.messages import t

SKIP = {"heading", "rich_text", "image", "divider", "computed_display", "payment_fixed", "payment_computed",
        "signature"}


def _label(block: dict[str, Any], locale: str) -> str:
    lab = block.get("label") or {}
    return str(lab.get(locale) or lab.get("fr") or lab.get("en") or block["id"])[:250]


def _var_name(block: dict[str, Any], used: set[str]) -> str:
    base = re.sub(r"[^A-Za-z0-9_]", "_", block.get("varName") or block.get("variableName") or block["id"])[:28] or "v"
    if not base[0].isalpha():
        base = f"v{base}"[:28]
    name, i = base, 2
    while name.lower() in used:
        name = f"{base[:25]}_{i}"
        i += 1
    used.add(name.lower())
    return name


class Column:
    def __init__(self, name: str, label: str, kind: str, values: dict[int, str] | None = None,
                 getter: Any = None) -> None:
        self.name, self.label, self.kind, self.values, self.getter = name, label, kind, values or {}, getter


def build_columns(schema: dict[str, Any], locale: str) -> list[Column]:
    used: set[str] = set()
    cols = [
        Column("response_id", "ID", "str", getter=lambda s: str(s.id)),
        Column("submitted_at", t("export.column.submitted_at", locale), "str",
               getter=lambda s: s.submitted_at.isoformat() if s.submitted_at else ""),
        Column("status", t("export.column.status", locale), "str", getter=lambda s: s.status),
        Column("payment_status", t("export.column.payment_status", locale), "str", getter=lambda s: s.payment_status),
        Column("amount", t("export.column.amount", locale), "num", getter=lambda s: s.amount_due),
        Column("source", t("export.column.source", locale), "str", getter=lambda s: s.source or ""),
        Column("lang", t("export.column.locale", locale), "str", getter=lambda s: s.locale),
    ]
    used.update(c.name for c in cols)
    for page in schema.get("pages", []):
        for b in page.get("blocks", []):
            if b["type"] in SKIP:
                continue
            bid, label = b["id"], _label(b, locale)
            opts = b.get("options") or []
            codes = {o["id"]: int(o.get("code") or i + 1) for i, o in enumerate(opts)}
            value_labels = {codes[o["id"]]: _label(o, locale) for o in opts}
            if b["type"] in ("single_choice", "dropdown"):
                cols.append(Column(_var_name(b, used), label, "num", value_labels,
                                   getter=lambda s, bid=bid, codes=codes: codes.get((s.answers or {}).get(bid))))
            elif b["type"] in ("multi_choice",):
                for o in opts:  # one 0/1 dummy per option, the standard for statistical packages
                    name = _var_name({"id": f"{b.get("varName") or b.get("variableName") or bid}_{o['id']}"}, used)
                    cols.append(Column(name, f"{label}: {_label(o, locale)}", "num", {0: "Non" if locale == "fr" else
                                       "No", 1: "Oui" if locale == "fr" else "Yes"},
                                       getter=lambda s, bid=bid, oid=o["id"]: int(oid in ((s.answers or {}).get(bid)
                                                                                         or []))))
            elif b["type"] in ("product_choice", "ticket_choice"):
                for o in opts:
                    name = _var_name({"id": f"{b.get("varName") or b.get("variableName") or bid}_{o['id']}"}, used)
                    cols.append(Column(name, f"{label}: {_label(o, locale)}", "num", getter=lambda s, bid=bid, oid=o[
                        "id"]: ((s.answers or {}).get(bid) or {}).get(oid)))
            elif b["type"] == "yes_no":
                yes, no = ("Oui", "Non") if locale == "fr" else ("Yes", "No")
                cols.append(Column(_var_name(b, used), label, "num", {1: yes, 0: no},
                                   getter=lambda s, bid=bid: None if (s.answers or {}).get(bid) is None else int(
                                       bool((s.answers or {}).get(bid)))))
            elif b["type"] in ("number", "rating", "linear_scale", "nps", "payment_open"):
                cols.append(Column(_var_name(b, used), label, "num",
                                   getter=lambda s, bid=bid: _to_float((s.answers or {}).get(bid))))
            elif b["type"] == "consent":
                cols.append(Column(_var_name(b, used), label, "num", {1: "Oui" if locale == "fr" else "Yes"},
                                   getter=lambda s, bid=bid: 1 if (s.answers or {}).get(bid) is True else None))
            else:
                cols.append(Column(_var_name(b, used), label, "str",
                                   getter=lambda s, bid=bid: _to_text((s.answers or {}).get(bid))))
    return cols


def _to_float(v: Any) -> float | None:
    try:
        return float(v) if v is not None and v != "" and not isinstance(v, bool) else None
    except (TypeError, ValueError):
        return None


def _to_text(v: Any) -> str:
    if v is None:
        return ""
    if isinstance(v, list):
        return "; ".join(map(str, v))
    if isinstance(v, dict):
        return "; ".join(f"{k}={x}" for k, x in v.items())
    return str(v)


def frame(subs: list[Any], cols: list[Column]) -> pl.DataFrame:
    data: dict[str, list[Any]] = {c.name: [c.getter(s) for s in subs] for c in cols}
    schema = {c.name: (pl.Float64 if c.kind == "num" else pl.Utf8) for c in cols}
    return pl.DataFrame(data, schema=schema)


def dictionary(cols: list[Column], locale: str) -> pl.DataFrame:
    return pl.DataFrame({
        t("export.dictionary.variable", locale): [c.name for c in cols],
        t("export.dictionary.label", locale): [c.label for c in cols],
        t("export.dictionary.type", locale): [c.kind for c in cols],
        t("export.dictionary.values", locale): ["; ".join(f"{k}={v}" for k, v in c.values.items()) for c in cols],
    })


def to_csv(df: pl.DataFrame) -> bytes:
    buf = io.BytesIO()
    df.write_csv(buf)
    return "﻿".encode() + buf.getvalue()  # BOM so Excel opens UTF-8 accents correctly


def to_xlsx(df: pl.DataFrame, dico: pl.DataFrame, sheet: str) -> bytes:
    buf = io.BytesIO()
    with xlsxwriter.Workbook(buf, {"in_memory": True}) as wb:
        df.write_excel(workbook=wb, worksheet=sheet[:31] or "Responses", autofit=True)
        dico.write_excel(workbook=wb, worksheet="Dictionnaire", autofit=True)
    return buf.getvalue()


def _stat_file(df: pl.DataFrame, cols: list[Column], kind: str) -> bytes:
    pdf = df  # pyreadstat 1.3 writes Polars frames directly
    labels: dict[str, str | None] = {c.name: c.label for c in cols}
    value_labels: dict[str, dict[int | float, str]] = {
        c.name: {float(k): v for k, v in c.values.items()} for c in cols if c.values}
    with tempfile.TemporaryDirectory() as tmp:
        path = Path(tmp) / f"export.{kind}"
        if kind == "sav":
            pyreadstat.write_sav(pdf, str(path), column_labels=labels, variable_value_labels=value_labels)
        else:
            dta_labels: dict[str, dict[int | float, str]] = {
                k: {int(x): y[:80] for x, y in v.items()} for k, v in value_labels.items()}
            pyreadstat.write_dta(pdf, str(path), column_labels={k: (v or "")[:80] for k, v in labels.items()},
                                 variable_value_labels=dta_labels, version=15)
        return path.read_bytes()


def to_sav(df: pl.DataFrame, cols: list[Column]) -> bytes:
    return _stat_file(df, cols, "sav")


def to_dta(df: pl.DataFrame, cols: list[Column]) -> bytes:
    return _stat_file(df, cols, "dta")
