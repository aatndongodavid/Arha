"""Organisation side responses table (F-REP-01..03, F-REP-07)."""

from __future__ import annotations

import uuid
from typing import Any

from fastapi import APIRouter, Depends, Query

from arha.core.context import Ctx, require_permission
from arha.core.features import has_feature
from arha.modules.forms import service as forms
from arha.modules.submissions import schemas as s
from arha.modules.submissions import service
from arha.modules.submissions.models import Submission
from arha.modules.trust import service as trust

router = APIRouter(prefix="/v1/orgs/{org_id}/forms/{form_id}/submissions", tags=["submissions"])


def _row(sub: Submission) -> s.SubmissionRow:
    return s.SubmissionRow(id=sub.id, status=sub.status, is_partial=sub.is_partial, last_field_id=sub.last_field_id,
                           payment_status=sub.payment_status, amount_due=sub.amount_due, currency=sub.currency,
                           locale=sub.locale, source=sub.source, answers=sub.answers or {},
                           computed=sub.computed or {}, form_version_id=sub.form_version_id,
                           started_at=sub.started_at, submitted_at=sub.submitted_at,
                           anonymized=sub.anonymized_at is not None)


@router.get("", response_model=s.SubmissionPage)
async def list_submissions(form_id: uuid.UUID, status: str | None = Query(default=None, max_length=20),
                           payment_status: str | None = Query(default=None, max_length=20),
                           q: str | None = Query(default=None, max_length=100), partial: bool = False,
                           cursor: str | None = Query(default=None, max_length=200),
                           limit: int = Query(default=50, ge=1, le=200),
                           ctx: Ctx = Depends(require_permission("responses:read"))) -> s.SubmissionPage:
    await forms.get_form(ctx.db, form_id)
    include_partial = partial and has_feature(ctx.org, "partial_responses")
    rows, nxt, total = await service.page(ctx.db, form_id=form_id, status=status, payment_status=payment_status,
                                          q=q, include_partial=include_partial, cursor=cursor, limit=limit)
    return s.SubmissionPage(items=[_row(r) for r in rows], next_cursor=nxt, total=total)


@router.get("/{submission_id}")
async def get_submission(form_id: uuid.UUID, submission_id: uuid.UUID,
                         ctx: Ctx = Depends(require_permission("responses:read"))) -> dict[str, Any]:
    sub = await service.get(ctx.db, form_id, submission_id)
    if sub.is_partial and not has_feature(ctx.org, "partial_responses"):
        from arha.core.errors import NotFound
        raise NotFound("submission_not_found")
    from arha.modules.forms.models import FormVersion
    version = await ctx.db.get(FormVersion, sub.form_version_id)
    events = await service.history(ctx.db, sub.id)
    from arha.modules.payments.service import payments_for_submission
    return {"submission": _row(sub).model_dump(mode="json"), "schema": version.schema if version else None,
            "history": [{"from": e.from_status, "to": e.to_status, "actor_id": e.actor_id, "at": e.created_at}
                        for e in events],
            "payments": await payments_for_submission(ctx.db, sub.id)}


@router.patch("/{submission_id}", response_model=s.SubmissionRow)
async def update_status(form_id: uuid.UUID, submission_id: uuid.UUID, body: s.StatusIn,
                        ctx: Ctx = Depends(require_permission("responses:update"))) -> s.SubmissionRow:
    sub = await service.get(ctx.db, form_id, submission_id)
    return _row(await service.set_status(ctx.db, sub, body.status, ctx.user_id))


@router.post("/anonymize", status_code=204)
async def anonymize(form_id: uuid.UUID, body: s.BulkIn,
                    ctx: Ctx = Depends(require_permission("responses:delete"))) -> None:
    from arha.modules.forms.models import FormVersion
    for sid in body.ids:
        sub = await service.get(ctx.db, form_id, sid)
        version = await ctx.db.get(FormVersion, sub.form_version_id)
        await service.anonymize(ctx.db, sub, version.schema if version else {})
    await trust.audit(ctx.db, "responses.anonymized", org_id=ctx.org_id, actor_id=ctx.user_id, target_type="form",
                      target_id=form_id, metadata={"count": len(body.ids)})


@router.post("/delete", status_code=204)
async def delete(form_id: uuid.UUID, body: s.BulkIn,
                 ctx: Ctx = Depends(require_permission("responses:delete"))) -> None:
    for sid in body.ids:
        await service.delete(ctx.db, await service.get(ctx.db, form_id, sid))
    await trust.audit(ctx.db, "responses.deleted", org_id=ctx.org_id, actor_id=ctx.user_id, target_type="form",
                      target_id=form_id, metadata={"count": len(body.ids)})
