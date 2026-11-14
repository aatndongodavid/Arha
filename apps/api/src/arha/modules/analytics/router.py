from __future__ import annotations

import uuid
from typing import Any, Literal

from fastapi import APIRouter, Depends, Query, Response

from arha.core.context import Ctx, require_permission
from arha.core.errors import AppError
from arha.core.features import require_feature
from arha.modules.analytics import exports, service
from arha.modules.forms import service as forms
from arha.modules.trust import service as trust

router = APIRouter(prefix="/v1/orgs/{org_id}/forms/{form_id}", tags=["analytics"])

MIME = {"csv": "text/csv; charset=utf-8",
        "xlsx": "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        "sav": "application/x-spss-sav", "dta": "application/x-stata-dta", "dictionary": "text/csv; charset=utf-8"}


async def _schema(ctx: Ctx, form_id: uuid.UUID) -> tuple[Any, dict[str, Any]]:
    form = await forms.get_form(ctx.db, form_id)
    version = await forms.current_version(ctx.db, form)
    return form, (version.schema if version else form.draft_schema)


@router.get("/summary")
async def summary(form_id: uuid.UUID, ctx: Ctx = Depends(require_permission("analytics:read"))) -> dict[str, Any]:
    _, schema = await _schema(ctx, form_id)
    subs = await service.completed(ctx.db, form_id)
    raw = await forms.funnel(ctx.db, form_id)
    from arha.modules.payments.service import summary as pay_summary

    return {"responses": len(subs), "questions": service.summarize(schema, subs, ctx.locale),
            "funnel": service.funnel_view(raw, schema, ctx.locale),
            "payments": await pay_summary(ctx.db, form_id) if forms.has_payments(schema) else None}


@router.get("/export")
async def export(form_id: uuid.UUID, format: Literal["csv", "xlsx", "sav", "dta", "dictionary"] = "csv",
                 lang: Literal["fr", "en"] | None = None,
                 ctx: Ctx = Depends(require_permission("responses:export"))) -> Response:
    """F-REP-04. CSV is in every plan, Excel, SPSS and Stata need `stats_exports` (Pro and above)."""
    if format == "csv":
        require_feature(ctx.org, "csv_export")
    elif format != "dictionary":
        require_feature(ctx.org, "stats_exports")
    locale = lang or ctx.locale
    form, schema = await _schema(ctx, form_id)
    cols = exports.build_columns(schema, locale)
    subs = await service.completed(ctx.db, form_id)
    df = exports.frame(subs, cols)
    if format == "csv":
        data = exports.to_csv(df)
    elif format == "dictionary":
        data = exports.to_csv(exports.dictionary(cols, locale))
    elif format == "xlsx":
        data = exports.to_xlsx(df, exports.dictionary(cols, locale), form.title)
    elif format == "sav":
        data = exports.to_sav(df, cols)
    elif format == "dta":
        data = exports.to_dta(df, cols)
    else:  # pragma: no cover
        raise AppError("export_format_unknown", 400)
    await trust.audit(ctx.db, "responses.exported", org_id=ctx.org_id, actor_id=ctx.user_id, target_type="form",
                      target_id=form_id, metadata={"format": format, "rows": len(subs)})
    ext = "csv" if format == "dictionary" else format
    name = f"{form.short_code}{'-dictionnaire' if format == 'dictionary' else ''}.{ext}"
    return Response(data, media_type=MIME[format], headers={"Content-Disposition": f'attachment; filename="{name}"',
                                                            "Cache-Control": "no-store"})


@router.get("/crosstab")
async def crosstab(form_id: uuid.UUID, row: str = Query(max_length=40), col: str = Query(max_length=40),
                   ctx: Ctx = Depends(require_permission("analytics:read"))) -> dict[str, Any]:
    """F-ANA-04 (V2, Pro): two question cross table with a chi-square test."""
    require_feature(ctx.org, "crosstabs")
    await _schema(ctx, form_id)
    subs = await service.completed(ctx.db, form_id)
    table: dict[str, dict[str, int]] = {}
    for s in subs:
        a, b = (s.answers or {}).get(row), (s.answers or {}).get(col)
        if a is None or b is None or isinstance(a, list | dict) or isinstance(b, list | dict):
            continue
        table.setdefault(str(a), {}).setdefault(str(b), 0)
        table[str(a)][str(b)] += 1
    rows_ = sorted(table)
    cols_ = sorted({c for r in table.values() for c in r})
    total = sum(sum(r.values()) for r in table.values())
    chi2 = 0.0
    if total:
        for r in rows_:
            rt = sum(table[r].values())
            for c in cols_:
                ct = sum(table[x].get(c, 0) for x in rows_)
                exp = rt * ct / total
                if exp:
                    chi2 += (table[r].get(c, 0) - exp) ** 2 / exp
    dof = max(0, (len(rows_) - 1) * (len(cols_) - 1))
    return {"rows": rows_, "columns": cols_, "table": table, "total": total, "chi2": round(chi2, 4), "dof": dof}
