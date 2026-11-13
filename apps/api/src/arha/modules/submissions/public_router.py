"""Public routes for respondents (F-PUB-01..09). Every route here is whitelisted with `public_route`."""

from __future__ import annotations

import html
import json
import uuid
from functools import lru_cache
from pathlib import Path
from typing import Any

from fastapi import APIRouter, Depends, File, Header, Response, UploadFile
from fastapi.responses import HTMLResponse, JSONResponse
from sqlalchemy import select, text

from arha.core import idempotency, ratelimit
from arha.core.context import Ctx, public_route
from arha.core.crypto import encrypt
from arha.core.errors import AppError, NotFound
from arha.core.features import plan_limit
from arha.core.ids import uuid7
from arha.core.plans import get_plans
from arha.core.storage import check_signature, sniff, storage
from arha.db.session import set_org
from arha.modules.forms import service as forms
from arha.modules.forms.models import Form, FormVersion
from arha.modules.orgs import service as orgs
from arha.modules.submissions import schemas as s
from arha.modules.submissions import service
from arha.modules.trust import service as trust
from arha.modules.trust.models import StoredFile
from arha.settings import get_settings

router = APIRouter(prefix="/v1/public", tags=["public"])
files_router = APIRouter(tags=["public"])


async def resolve(ctx: Ctx, code: str) -> tuple[Form, Any, FormVersion | None]:
    if len(code) > 16:
        raise NotFound("form_not_found")
    org_id = (await ctx.db.execute(text("select resolve_org('form_code', :c)"), {"c": code})).scalar()
    if org_id is None:
        raise NotFound("form_not_found")
    await set_org(ctx.db, org_id)
    form = (await ctx.db.execute(select(Form).where(Form.short_code == code))).scalar_one()
    org = await orgs.get_org(ctx.db, org_id)
    version = await forms.current_version(ctx.db, form)
    return form, org, version


def _provider_for(schema: dict[str, Any]) -> str:
    override = get_settings().payment_provider_override
    if override:
        return override
    return str(((schema.get("settings") or {}).get("payments") or {}).get("provider") or "notchpay")


@router.get("/forms/{code}")
async def get_public_form(code: str, ctx: Ctx = Depends(public_route)) -> dict[str, Any]:
    form, org, version = await resolve(ctx, code)
    reason = service.availability(form, org, await service.completed_count(ctx.db, form.id))
    if reason == "form_unavailable" or version is None:
        raise AppError("form_unavailable", 410)
    schema = version.schema
    payments = (schema.get("settings") or {}).get("payments") or {}
    plans = get_plans()
    tickets: dict[str, Any] = {}
    if forms.has_payments(schema):
        from arha.modules.payments.service import tickets_remaining
        tickets = await tickets_remaining(ctx.db, form.id)
    await forms.bump_funnel(ctx.db, form.id, "view")
    st = get_settings()
    return {
        "form_id": form.id, "version_id": version.id, "version": version.number, "code": form.short_code,
        "title": form.title, "schema": schema, "status": "closed" if reason == "form_closed" else "open",
        "organization": {"name": org.name, "slug": org.slug, "verified": org.verified_at is not None,
                         "verification_url": f"{st.arha_site_url}/verification/{org.slug}"},
        "branding_required": bool(plans.plans[org.plan_code].branding_required),
        "branding_url": f"{st.arha_site_url}/?ref={org.referral_code}",
        "payments": {"currency": payments.get("currency", org.currency),
                     "fee_bearer": payments.get("feeBearer", "org"),
                     "platform_fee_bps": plans.plans[org.plan_code].fee_bps,
                     "provider_fee_bps": _provider_fee_bps(_provider_for(schema))},
        "tickets": tickets,
    }


def _provider_fee_bps(provider: str) -> int:
    from arha.core.plans import get_countries

    p = get_countries().providers.get(provider)
    return p.estimated_fee_bps if p else 0


@lru_cache
def _forms_index() -> str | None:
    path = Path(get_settings().config_dir).parent / "apps" / "forms" / "dist" / "index.html"
    return path.read_text(encoding="utf-8") if path.exists() else None


@router.get("/forms/{code}/page", response_class=HTMLResponse)
async def public_page(code: str, ctx: Ctx = Depends(public_route)) -> HTMLResponse:
    """F-PUB-06: server rendered Open Graph tags so WhatsApp previews show title and description."""
    try:
        form, org, version = await resolve(ctx, code)
        schema = version.schema if version else {}
        loc = schema.get("defaultLocale", "fr")
        title = form.title
        desc = ((schema.get("description") or {}).get(loc) or org.name)[:200]
        available = version is not None and service.availability(
            form, org, await service.completed_count(ctx.db, form.id)) != "form_unavailable"
    except NotFound:
        title, desc, available = "Arha", "", False
    if not available:
        title, desc = "Arha", ""
    st = get_settings()
    meta = (f'<title>{html.escape(title)}</title>'
            f'<meta property="og:title" content="{html.escape(title)}">'
            f'<meta property="og:description" content="{html.escape(desc)}">'
            f'<meta property="og:type" content="website">'
            f'<meta property="og:url" content="{html.escape(st.arha_forms_url)}/{html.escape(code)}">'
            f'<meta property="og:image" content="{html.escape(st.arha_site_url)}/og-default.png">'
            f'<meta name="description" content="{html.escape(desc)}">')
    index = _forms_index() or "<!doctype html><html><head><meta charset=\"utf-8\"></head><body></body></html>"
    page = index.replace("<!--OG-->", meta) if "<!--OG-->" in index else index.replace("</head>", meta + "</head>")
    headers = {"Cache-Control": "public, max-age=60",
               "Content-Security-Policy": "default-src 'self'; img-src 'self' data: https:; style-src 'self'; "
                                          f"connect-src 'self' {st.arha_api_url}; frame-ancestors 'self'"}
    return HTMLResponse(page, headers=headers)


@router.post("/forms/{code}/submissions", response_model=s.SubmissionResult)
async def submit(code: str, body: s.SubmissionIn, response: Response,
                 idempotency_key: str | None = Header(default=None, alias="Idempotency-Key"),
                 ctx: Ctx = Depends(public_route)) -> JSONResponse:
    await ratelimit.limit("submission", ctx.ip_hash or "", code)
    form, org, version = await resolve(ctx, code)
    target = version
    if version is None or body.form_version_id != version.id:
        target = await ctx.db.get(FormVersion, body.form_version_id)
        if target is None or target.form_id != form.id:
            raise AppError("submission_version_mismatch", 409)
    if not body.partial:
        key = idempotency.require_key(idempotency_key)
        body_hash = idempotency.request_hash(body.model_dump(mode="json"))
        replay = await idempotency.lookup(ctx.db, "submission", key, body_hash)
        if replay:
            return JSONResponse(replay["response"], status_code=200)
    reason = service.availability(form, org, await service.completed_count(ctx.db, form.id))
    already = await ctx.db.get(service.Submission, body.id)
    if reason and not (already and already.submitted_at and not already.is_partial):
        raise AppError(reason, 410 if reason == "form_unavailable" else 403)
    result, status = await service.intake(ctx.db, form=form, org=org, version=target, payload=body,
                                          provider=_provider_for(target.schema))
    payload = s.SubmissionResult(**result).model_dump(mode="json") if status != 202 else json.loads(
        json.dumps(result, default=str))
    if not body.partial:
        await idempotency.store(ctx.db, "submission", key, body_hash, payload, status)
    return JSONResponse(payload, status_code=status)


@router.post("/forms/{code}/submissions/{submission_id}/resume-code", response_model=s.ResumeCodeOut)
async def resume_code(code: str, submission_id: uuid.UUID, ctx: Ctx = Depends(public_route)) -> s.ResumeCodeOut:
    """F-PUB-05: a six character code to finish later, valid 30 days, scoped to this draft only."""
    await ratelimit.limit("resume", ctx.ip_hash or "", "issue")
    form, _, _ = await resolve(ctx, code)
    sub = await service.get_for_update(ctx.db, submission_id)
    if sub is None or sub.form_id != form.id or not sub.is_partial:
        raise NotFound("submission_not_found")
    value, expires = await service.issue_resume_code(ctx.db, sub)
    return s.ResumeCodeOut(code=value, expires_at=expires)


@router.post("/forms/{code}/resume")
async def resume(code: str, body: s.ResumeIn, ctx: Ctx = Depends(public_route)) -> dict[str, Any]:
    await ratelimit.limit("resume", ctx.ip_hash or "")  # 5 attempts per hour per IP
    form, _, _ = await resolve(ctx, code)
    sub = await service.find_by_resume(ctx.db, form.id, body.code)
    return {"id": sub.id, "form_version_id": sub.form_version_id, "answers": sub.answers,
            "last_field_id": sub.last_field_id, "locale": sub.locale}


@router.post("/forms/{code}/events", status_code=204)
async def funnel_event(code: str, body: s.FunnelIn, ctx: Ctx = Depends(public_route)) -> None:
    await ratelimit.limit("submission", ctx.ip_hash or "", f"{code}:event")
    form, _, _ = await resolve(ctx, code)
    await forms.bump_funnel(ctx.db, form.id, body.step)
    if body.field_id:
        await forms.bump_funnel(ctx.db, form.id, f"field:{body.field_id}"[:60])


@router.post("/forms/{code}/report", status_code=202)
async def report(code: str, body: s.ReportIn, ctx: Ctx = Depends(public_route)) -> dict[str, str]:
    """F-PUB-08: the report reaches the internal console with a snapshot of the content."""
    await ratelimit.limit("report", ctx.ip_hash or "")
    form, org, version = await resolve(ctx, code)
    snapshot = {"title": form.title, "version": version.number if version else None,
                "schema": version.schema if version else form.draft_schema, "organization": org.name}
    await trust.create_report(ctx.db, form_id=form.id, reason=body.reason, details=body.details,
                              contact_enc=encrypt(body.contact) if body.contact else None, snapshot=snapshot)
    return {"status": "received"}


@router.post("/forms/{code}/files", status_code=201)
async def upload(code: str, file: UploadFile = File(...), ctx: Ctx = Depends(public_route)) -> dict[str, str]:
    """S-10: real type check by magic number, size limit by plan, private storage, separate domain."""
    await ratelimit.limit("submission", ctx.ip_hash or "", f"{code}:file")
    form, org, version = await resolve(ctx, code)
    if version is None or service.availability(form, org, 0) == "form_unavailable":
        raise AppError("form_unavailable", 410)
    max_mb = plan_limit(org, "max_file_mb") or 10
    data = await file.read(max_mb * 1024 * 1024 + 1)
    if len(data) > max_mb * 1024 * 1024:
        raise AppError("file_too_large", 413)
    mime = sniff(data)
    if mime not in ("application/pdf", "image/png", "image/jpeg", "image/webp"):
        raise AppError("file_type_not_allowed", 415)
    key = f"{org.id}/{form.id}/{uuid7()}"
    storage().put(key, data)
    ctx.db.add(StoredFile(id=uuid7(), key=key, content_type=mime, size_bytes=len(data), purpose="response",
                          scan_status="pending"))
    from arha.core import jobs
    jobs.enqueue(ctx.db, "submissions.scan_file", org_id=str(org.id), key=key)
    return {"key": key, "content_type": mime}


@router.get("/orgs/{slug}/verification")
async def verification(slug: str, ctx: Ctx = Depends(public_route)) -> dict[str, Any]:
    """F-PUB-07: the verified badge links to this page hosted by Arha."""
    org_id = (await ctx.db.execute(text("select resolve_org('org_slug', :s)"), {"s": slug[:64]})).scalar()
    if org_id is None:
        raise NotFound("organization_not_found")
    await set_org(ctx.db, org_id)
    org = await orgs.get_org(ctx.db, org_id)
    return {"name": org.name, "verified": org.verified_at is not None, "verified_at": org.verified_at,
            "suspended": org.suspended_at is not None}


@files_router.get("/files/{key:path}")
async def download(key: str, e: int, s: str, ctx: Ctx = Depends(public_route)) -> Response:
    """Signed, 5 minute, attachment-only download (S-10)."""
    if not check_signature(key, e, s):
        raise NotFound()
    data = storage().get(key)
    mime = sniff(data) or "application/octet-stream"
    return Response(data, media_type=mime, headers={
        "Content-Disposition": f'attachment; filename="{key.rsplit("/", 1)[-1]}"',
        "X-Content-Type-Options": "nosniff", "Cache-Control": "private, no-store",
        "Content-Security-Policy": "default-src 'none'; sandbox"})


__all__ = ["router", "files_router", "json"]
