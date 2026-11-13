from __future__ import annotations

import uuid

from fastapi import APIRouter, Depends, Query

from arha.core.context import Ctx, authenticated, require_permission
from arha.core.errors import AppError, NotFound
from arha.core.messages import t
from arha.modules.forms import schemas as s
from arha.modules.forms import service, templates
from arha.modules.forms.models import Form
from arha.modules.identity import service as identity
from arha.modules.logic import analysis
from arha.modules.trust import service as trust

router = APIRouter(prefix="/v1", tags=["forms"])


def _summary(form: Form, responses: int) -> s.FormSummary:
    return s.FormSummary(id=form.id, title=form.title, status=form.status, short_code=form.short_code,
                         folder_id=form.folder_id, updated_at=form.updated_at, responses=responses,
                         public_url=service.public_url(form.short_code))


async def _out(ctx: Ctx, form: Form) -> s.FormOut:
    from arha.modules.submissions.service import count_by_form

    version = await service.current_version(ctx.db, form)
    counts = await count_by_form(ctx.db, [form.id])
    unpublished = version is None or version.schema_hash != service.schema_hash(form.draft_schema)
    return s.FormOut(**_summary(form, counts.get(form.id, 0)).model_dump(), draft_schema=form.draft_schema,
                     draft_revision=form.draft_revision, current_version=version.number if version else None,
                     closes_at=form.closes_at, max_responses=form.max_responses, retention_days=form.retention_days,
                     allow_embed=form.allow_embed, publish_block_reason=form.publish_block_reason,
                     has_unpublished_changes=unpublished)


@router.get("/templates", response_model=list[s.TemplateOut])
async def list_templates(ctx: Ctx = Depends(authenticated)) -> list[dict[str, object]]:
    return templates.list_templates()


@router.get("/orgs/{org_id}/forms", response_model=list[s.FormSummary])
async def list_forms(folder_id: uuid.UUID | None = None, q: str | None = Query(default=None, max_length=100),
                     sort: str = Query(default="updated", pattern="^(updated|title|created)$"),
                     limit: int = Query(default=50, ge=1, le=200), offset: int = Query(default=0, ge=0),
                     ctx: Ctx = Depends(require_permission("forms:read"))) -> list[s.FormSummary]:
    rows = await service.list_forms(ctx.db, folder_id=folder_id, query=q, sort=sort, limit=limit, offset=offset)
    return [_summary(f, n) for f, n in rows]


@router.post("/orgs/{org_id}/forms", response_model=s.FormOut, status_code=201)
async def create_form(body: s.FormCreateIn, ctx: Ctx = Depends(require_permission("forms:edit"))) -> s.FormOut:
    schema = None
    if body.template:
        schema = templates.template_schema(body.template)
        if schema is None:
            raise NotFound("not_found")
    form = await service.create_form(ctx.db, user_id=ctx.user_id, title=body.title, folder_id=body.folder_id,
                                     schema=schema, locale=body.locale)
    await trust.audit(ctx.db, "form.created", org_id=ctx.org_id, actor_id=ctx.user_id, target_type="form",
                      target_id=form.id, metadata={"template": body.template})
    return await _out(ctx, form)


@router.get("/orgs/{org_id}/forms/{form_id}", response_model=s.FormOut)
async def get_form(form_id: uuid.UUID, ctx: Ctx = Depends(require_permission("forms:read"))) -> s.FormOut:
    return await _out(ctx, await service.get_form(ctx.db, form_id))


@router.patch("/orgs/{org_id}/forms/{form_id}", response_model=s.FormOut)
async def update_form(form_id: uuid.UUID, body: s.FormUpdateIn,
                      ctx: Ctx = Depends(require_permission("forms:edit"))) -> s.FormOut:
    form = await service.get_form(ctx.db, form_id)
    data = body.model_dump(exclude_unset=True)
    if "title" in data:
        form.title = data["title"]
    if data.get("move_to_root"):
        form.folder_id = None
    elif "folder_id" in data:
        form.folder_id = data["folder_id"]
    for key in ("closes_at", "max_responses", "retention_days", "allow_embed"):
        if key in data:
            setattr(form, key, data[key])
    return await _out(ctx, form)


@router.put("/orgs/{org_id}/forms/{form_id}/draft", response_model=s.FormOut)
async def save_draft(form_id: uuid.UUID, body: s.DraftIn,
                     ctx: Ctx = Depends(require_permission("forms:edit"))) -> s.FormOut:
    form = await service.get_form(ctx.db, form_id)
    form = await service.save_draft(ctx.db, form, body.schema_, body.revision)
    return await _out(ctx, form)


@router.post("/orgs/{org_id}/forms/{form_id}/validate", response_model=list[s.IssueOut])
async def validate(form_id: uuid.UUID, ctx: Ctx = Depends(require_permission("forms:read"))) -> list[s.IssueOut]:
    form = await service.get_form(ctx.db, form_id)
    issues = [s.IssueOut(**i.as_dict()) for i in analysis.analyze(service.validate_schema(form.draft_schema))]
    for m in trust.scan_schema(form.draft_schema):
        issues.append(s.IssueOut(severity="error", code="abuse_term", target=m.path, detail=m.term))
    return issues


@router.post("/orgs/{org_id}/forms/{form_id}/publish", response_model=s.PublishOut)
async def publish(form_id: uuid.UUID, ctx: Ctx = Depends(require_permission("forms:publish"))) -> s.PublishOut:
    form = await service.get_form(ctx.db, form_id)
    user = await identity.get_user(ctx.db, ctx.user_id)
    try:
        version, warnings = await service.publish(ctx.db, form, user_id=ctx.user_id,
                                                  email_verified=user.email_verified_at is not None,
                                                  ip_hash=ctx.ip_hash)
    except AppError as exc:
        if exc.code == "publication_blocked":
            # Persist the block reason even though the request fails.
            await ctx.db.commit()
        raise
    return s.PublishOut(version=version.number, public_url=service.public_url(form.short_code),
                        warnings=[s.IssueOut(**w.as_dict()) for w in warnings])


@router.post("/orgs/{org_id}/forms/{form_id}/publication-review", status_code=202)
async def request_review(form_id: uuid.UUID, body: s.ReviewIn,
                         ctx: Ctx = Depends(require_permission("forms:publish"))) -> dict[str, str]:
    """F-ADM-01: the creator sees why publication is blocked and can ask for a manual review."""
    form = await service.get_form(ctx.db, form_id)
    matches = trust.scan_schema(form.draft_schema)
    if not matches:
        return {"status": "not_needed"}
    await trust.request_publication_review(ctx.db, form.id, matches, body.message)
    await trust.audit(ctx.db, "form.review_requested", org_id=ctx.org_id, actor_id=ctx.user_id,
                      target_type="form", target_id=form.id)
    return {"status": "pending"}


@router.get("/orgs/{org_id}/forms/{form_id}/versions", response_model=list[s.VersionOut])
async def versions(form_id: uuid.UUID, ctx: Ctx = Depends(require_permission("forms:read"))) -> list[s.VersionOut]:
    form = await service.get_form(ctx.db, form_id)
    return [s.VersionOut(id=v.id, number=v.number, published_at=v.published_at, published_by=v.published_by,
                         current=v.id == form.current_version_id) for v in await service.list_versions(ctx.db, form_id)]


@router.get("/orgs/{org_id}/forms/{form_id}/versions/{version_id}")
async def version_detail(form_id: uuid.UUID, version_id: uuid.UUID,
                         ctx: Ctx = Depends(require_permission("forms:read"))) -> dict[str, object]:
    v = await service.get_version(ctx.db, version_id)
    if v.form_id != form_id:
        raise NotFound("version_not_found")
    return {"id": v.id, "number": v.number, "schema": v.schema, "published_at": v.published_at}


@router.post("/orgs/{org_id}/forms/{form_id}/versions/{version_id}/restore", response_model=s.FormOut)
async def restore(form_id: uuid.UUID, version_id: uuid.UUID,
                  ctx: Ctx = Depends(require_permission("forms:edit"))) -> s.FormOut:
    form = await service.get_form(ctx.db, form_id)
    v = await service.get_version(ctx.db, version_id)
    if v.form_id != form.id:
        raise NotFound("version_not_found")
    return await _out(ctx, await service.restore_version(ctx.db, form, v, ctx.user_id))


@router.post("/orgs/{org_id}/forms/{form_id}/close", response_model=s.FormOut)
async def close(form_id: uuid.UUID, ctx: Ctx = Depends(require_permission("forms:publish"))) -> s.FormOut:
    form = await service.get_form(ctx.db, form_id)
    if form.status == "published":
        form.status = "closed"
    return await _out(ctx, form)


@router.post("/orgs/{org_id}/forms/{form_id}/reopen", response_model=s.FormOut)
async def reopen(form_id: uuid.UUID, ctx: Ctx = Depends(require_permission("forms:publish"))) -> s.FormOut:
    form = await service.get_form(ctx.db, form_id)
    if form.status == "closed" and form.current_version_id:
        form.status = "published"
    return await _out(ctx, form)


@router.post("/orgs/{org_id}/forms/{form_id}/duplicate", response_model=s.FormOut, status_code=201)
async def duplicate(form_id: uuid.UUID, ctx: Ctx = Depends(require_permission("forms:edit"))) -> s.FormOut:
    form = await service.get_form(ctx.db, form_id)
    copy_ = await service.duplicate(ctx.db, form, ctx.user_id, t("form.copy_suffix", ctx.locale))
    return await _out(ctx, copy_)


@router.delete("/orgs/{org_id}/forms/{form_id}", status_code=204)
async def delete_form(form_id: uuid.UUID, ctx: Ctx = Depends(require_permission("forms:edit"))) -> None:
    from arha.core import clock

    form = await service.get_form(ctx.db, form_id)
    form.deleted_at = clock.now()
    form.status = "closed"
    await trust.audit(ctx.db, "form.deleted", org_id=ctx.org_id, actor_id=ctx.user_id, target_type="form",
                      target_id=form.id)
