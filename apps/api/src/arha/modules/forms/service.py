"""Forms, drafts, immutable versions and publication (F-EDI-01..10, F-ADM-01)."""

from __future__ import annotations

import copy
import hashlib
import json
import uuid
from typing import Any

import nh3
from pydantic import ValidationError
from sqlalchemy import func, select, text, update
from sqlalchemy.ext.asyncio import AsyncSession

from arha.core import clock
from arha.core.errors import AppError, Conflict, NotFound
from arha.core.ids import uuid7
from arha.core.security import short_code
from arha.modules.forms.models import Form, FormFunnel, FormVersion
from arha.modules.forms.schema_models import ArhaForm
from arha.modules.logic import analysis
from arha.modules.logic.engine import PAYMENT_TYPES
from arha.modules.trust import service as trust
from arha.settings import get_settings

RICH_TAGS = {"b", "strong", "i", "em", "u", "a", "br", "p", "ul", "ol", "li"}


def public_url(code: str) -> str:
    return f"{get_settings().arha_forms_url}/{code}"


def empty_schema(title: str, locale: str = "fr") -> dict[str, Any]:
    return {
        "schemaVersion": 1, "defaultLocale": locale, "locales": ["fr", "en"],
        "settings": {
            "theme": {"primary": "#C9621B", "background": "#FCF9F4", "font": "system", "logoKey": None,
                      "coverKey": None},
            "closing": {"closesAt": None, "maxResponses": None, "message": {}},
            "ending": {"message": {"fr": "Merci, votre réponse a bien été enregistrée.",
                                   "en": "Thank you, your response has been recorded."}, "redirectUrl": None},
            "payments": {"enabled": False, "currency": "XAF", "feeBearer": "org", "provider": "notchpay"},
            "consent": {"required": True, "textVersion": "2026-11"},
            "saveAndResume": True, "showProgress": True,
        },
        "variables": [], "pages": [{"id": "p1", "title": {locale: title}, "blocks": []}], "rules": [],
    }


def _sanitize(node: Any, key: str | None = None) -> Any:
    if isinstance(node, dict):
        return {k: _sanitize(v, k) for k, v in node.items()}
    if isinstance(node, list):
        return [_sanitize(v, key) for v in node]
    if isinstance(node, str) and key in ("fr", "en"):
        return nh3.clean(node, tags=RICH_TAGS, attributes={"a": {"href"}}, url_schemes={"https", "mailto"},
                         link_rel="noopener noreferrer nofollow")
    return node


def validate_schema(schema: dict[str, Any]) -> dict[str, Any]:
    """Structural validation against form.schema.json (S-08) and rich text sanitation."""
    try:
        ArhaForm.model_validate(schema)
    except ValidationError as exc:
        errors = [{"loc": [str(p) for p in e["loc"]], "type": e["type"]} for e in exc.errors()[:20]]
        raise AppError("form_schema_invalid", 422, extra={"errors": errors}) from exc
    if len(json.dumps(schema)) > 1_000_000:
        raise AppError("form_schema_invalid", 422)
    return _sanitize(schema)  # type: ignore[no-any-return]


def schema_hash(schema: dict[str, Any]) -> str:
    return hashlib.sha256(json.dumps(schema, sort_keys=True, separators=(",", ":")).encode()).hexdigest()


async def create_form(db: AsyncSession, *, user_id: uuid.UUID, title: str, folder_id: uuid.UUID | None,
                      schema: dict[str, Any] | None, locale: str) -> Form:
    draft = validate_schema(schema) if schema else empty_schema(title, locale)
    for _ in range(5):
        code = short_code(8)
        exists = (await db.execute(text("select resolve_org('form_code', :c)"), {"c": code})).scalar()
        if exists is None:
            break
    form = Form(id=uuid7(), title=title, folder_id=folder_id, draft_schema=draft, short_code=code,
                created_by=user_id)
    db.add(form)
    await db.flush()
    return form


async def get_form(db: AsyncSession, form_id: uuid.UUID) -> Form:
    form = await db.get(Form, form_id)
    if form is None or form.deleted_at is not None:
        raise NotFound("form_not_found")
    return form


async def list_forms(db: AsyncSession, *, folder_id: uuid.UUID | None, query: str | None, sort: str,
                     limit: int, offset: int) -> list[tuple[Form, int]]:
    from arha.modules.submissions.service import count_by_form  # service to service

    stmt = select(Form).where(Form.deleted_at.is_(None))
    if folder_id:
        stmt = stmt.where(Form.folder_id == folder_id)
    if query:
        stmt = stmt.where(Form.title.ilike(f"%{query.replace('%', '').replace('_', '')}%"))
    order = {"updated": Form.updated_at.desc(), "title": Form.title.asc(), "created": Form.created_at.desc()}
    stmt = stmt.order_by(order.get(sort, Form.updated_at.desc()), Form.id).limit(limit).offset(offset)
    forms = list((await db.execute(stmt)).scalars())
    counts = await count_by_form(db, [f.id for f in forms])
    return [(f, counts.get(f.id, 0)) for f in forms]


async def save_draft(db: AsyncSession, form: Form, schema: dict[str, Any], revision: int) -> Form:
    """Optimistic concurrency: the client sends the revision it edited (F-EDI-02)."""
    clean = validate_schema(schema)
    res = await db.execute(update(Form).where(Form.id == form.id, Form.draft_revision == revision)
                           .values(draft_schema=clean, draft_revision=revision + 1, updated_at=clock.now())
                           .returning(Form.draft_revision))
    if res.scalar_one_or_none() is None:
        raise Conflict("form_revision_conflict", current_revision=form.draft_revision)
    await db.refresh(form)
    return form


async def current_version(db: AsyncSession, form: Form) -> FormVersion | None:
    return await db.get(FormVersion, form.current_version_id) if form.current_version_id else None


async def list_versions(db: AsyncSession, form_id: uuid.UUID) -> list[FormVersion]:
    stmt = select(FormVersion).where(FormVersion.form_id == form_id).order_by(FormVersion.number.desc())
    return list((await db.execute(stmt)).scalars())


async def get_version(db: AsyncSession, version_id: uuid.UUID) -> FormVersion:
    v = await db.get(FormVersion, version_id)
    if v is None:
        raise NotFound("version_not_found")
    return v


def has_payments(schema: dict[str, Any]) -> bool:
    return any(b["type"] in PAYMENT_TYPES for p in schema.get("pages", []) for b in p.get("blocks", []))


async def publish(db: AsyncSession, form: Form, *, user_id: uuid.UUID, email_verified: bool,
                  ip_hash: str | None) -> tuple[FormVersion, list[analysis.Issue]]:
    if not email_verified:
        raise AppError("email_not_verified", 403)
    if form.status == "suspended":
        raise AppError("form_unavailable", 403)
    schema = validate_schema(form.draft_schema)
    issues = analysis.analyze(schema)
    if analysis.has_errors(issues):
        raise AppError("form_logic_invalid", 422, extra={"issues": [i.as_dict() for i in issues]})

    # S-20 anti-phishing filter. A positive match blocks publication unless the platform approved it.
    matches = trust.scan_schema(schema)
    if matches and not await trust.approved_review_exists(db, form.id):
        form.publish_block_reason = "abuse_terms"
        raise AppError("publication_blocked", 422, extra={"matches": [m.__dict__ for m in matches]})

    if has_payments(schema):
        from arha.modules.payments.service import ensure_can_collect  # service to service
        await ensure_can_collect(db, schema)

    number = int((await db.execute(select(func.coalesce(func.max(FormVersion.number), 0))
                                   .where(FormVersion.form_id == form.id))).scalar_one()) + 1
    version = FormVersion(id=uuid7(), form_id=form.id, number=number, schema=copy.deepcopy(schema),
                          schema_hash=schema_hash(schema), published_by=user_id)
    db.add(version)
    await db.flush()
    closing = (schema.get("settings") or {}).get("closing") or {}
    form.current_version_id = version.id
    form.status = "published"
    form.publish_block_reason = None
    if closing.get("maxResponses"):
        form.max_responses = closing["maxResponses"]
    form.updated_at = clock.now()

    if has_payments(schema):
        from arha.modules.payments.service import sync_ticket_categories
        await sync_ticket_categories(db, form.id, schema)

    await trust.audit(db, "form.published", org_id=form.organization_id, actor_id=user_id, target_type="form",
                      target_id=form.id, ip_hash=ip_hash, metadata={"version": number})
    await bump_funnel(db, form.id, "published")
    return version, [i for i in issues if i.severity == "warning"]


async def restore_version(db: AsyncSession, form: Form, version: FormVersion, user_id: uuid.UUID) -> Form:
    """F-EDI-03: restoring creates a new draft from the version; published versions stay immutable."""
    form.draft_schema = copy.deepcopy(version.schema)
    form.draft_revision += 1
    form.updated_at = clock.now()
    await trust.audit(db, "form.version_restored", org_id=form.organization_id, actor_id=user_id,
                      target_type="form", target_id=form.id, metadata={"version": version.number})
    return form


async def duplicate(db: AsyncSession, form: Form, user_id: uuid.UUID, title_suffix: str) -> Form:
    return await create_form(db, user_id=user_id, title=f"{form.title} {title_suffix}"[:200],
                             folder_id=form.folder_id, schema=copy.deepcopy(form.draft_schema), locale="fr")


async def bump_funnel(db: AsyncSession, form_id: uuid.UUID, step: str, by: int = 1) -> None:
    """Aggregated daily counters, no cookie, no identifier (F-ANA-02)."""
    day = clock.now().astimezone(clock.DOUALA).date()
    await db.execute(text(
        "insert into form_funnel (organization_id, form_id, day, step, value) values (app_org(), :f, :d, :s, :v) "
        "on conflict (form_id, day, step) do update set value = form_funnel.value + excluded.value"),
        {"f": form_id, "d": day, "s": step, "v": by})


async def funnel(db: AsyncSession, form_id: uuid.UUID) -> dict[str, int]:
    rows = (await db.execute(select(FormFunnel.step, func.sum(FormFunnel.value)).where(
        FormFunnel.form_id == form_id).group_by(FormFunnel.step))).all()
    return {step: int(total) for step, total in rows}
