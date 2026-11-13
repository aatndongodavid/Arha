"""Audit trail (hash chained, S-16), anti-phishing publication filter (S-20), reports, verification."""

from __future__ import annotations

import hashlib
import json
import re
import unicodedata
import uuid
from dataclasses import dataclass
from functools import lru_cache
from typing import Any

import yaml
from sqlalchemy import select, text
from sqlalchemy.ext.asyncio import AsyncSession

from arha.core import clock
from arha.core.ids import uuid7
from arha.modules.trust.models import AbuseReport, AuditEvent, PublicationReview, VerificationRequest
from arha.settings import get_settings


def canonical_json(data: Any) -> str:
    return json.dumps(data, sort_keys=True, separators=(",", ":"), default=str, ensure_ascii=False)


def _event_body(e: AuditEvent) -> dict[str, Any]:
    return {"id": str(e.id), "organization_id": str(e.organization_id) if e.organization_id else None,
            "actor_id": str(e.actor_id) if e.actor_id else None, "action": e.action,
            "target_type": e.target_type, "target_id": e.target_id, "metadata": e.metadata_,
            "created_at": e.created_at.isoformat()}


async def audit(db: AsyncSession, action: str, *, org_id: uuid.UUID | None, actor_id: uuid.UUID | None,
                target_type: str | None = None, target_id: Any = None, ip_hash: str | None = None,
                metadata: dict[str, Any] | None = None) -> AuditEvent:
    """Append an audit event. hash = sha256(previous_hash || canonical_json(event))."""
    lock_key = str(org_id) if org_id else "platform"
    await db.execute(text("select pg_advisory_xact_lock(hashtext(:k))"), {"k": f"audit:{lock_key}"})
    prev_stmt = select(AuditEvent.hash).order_by(AuditEvent.created_at.desc(), AuditEvent.id.desc()).limit(1)
    prev_stmt = prev_stmt.where(AuditEvent.organization_id == org_id) if org_id else prev_stmt.where(
        AuditEvent.organization_id.is_(None))
    previous = (await db.execute(prev_stmt)).scalar_one_or_none()
    event = AuditEvent(id=uuid7(), organization_id=org_id, actor_id=actor_id, action=action,
                       target_type=target_type, target_id=str(target_id) if target_id is not None else None,
                       ip_hash=ip_hash, metadata_=metadata or {}, created_at=clock.now(), previous_hash=previous)
    event.hash = hashlib.sha256(((previous or "") + canonical_json(_event_body(event))).encode()).hexdigest()
    db.add(event)
    await db.flush()
    return event


def verify_chain(events: list[AuditEvent]) -> bool:
    previous: str | None = None
    for e in events:
        if e.previous_hash != previous:
            return False
        expected = hashlib.sha256(((previous or "") + canonical_json(_event_body(e))).encode()).hexdigest()
        if expected != e.hash:
            return False
        previous = e.hash
    return True


# ------------------------------------------------------------------ anti-phishing filter


def normalize(value: str) -> str:
    stripped = "".join(c for c in unicodedata.normalize("NFKD", value) if not unicodedata.combining(c))
    return re.sub(r"[^a-z0-9]+", " ", stripped.lower()).strip()


@lru_cache
def _terms() -> list[tuple[str, str]]:
    raw = yaml.safe_load((get_settings().config_dir / "abuse_terms.yaml").read_text(encoding="utf-8"))
    return [(lang, normalize(term)) for lang in ("fr", "en") for term in raw.get(lang, [])]


def luhn_valid(digits: str) -> bool:
    total, parity = 0, len(digits) % 2
    for i, ch in enumerate(digits):
        d = int(ch)
        if i % 2 == parity:
            d *= 2
            if d > 9:
                d -= 9
        total += d
    return total % 10 == 0


_CARD = re.compile(r"(?:\d[ -]?){13,19}")
_SKIP_KEYS = {"id", "type", "op", "action", "target", "field", "ref", "logoKey", "coverKey", "provider",
              "currency", "feeBearer", "font", "primary", "background", "redirectUrl", "defaultLocale",
              "locales", "textVersion"}


@dataclass(frozen=True)
class AbuseMatch:
    path: str
    term: str
    lang: str


def _walk_texts(node: Any, path: str = "") -> list[tuple[str, str]]:
    out: list[tuple[str, str]] = []
    if isinstance(node, str):
        out.append((path, node))
    elif isinstance(node, dict):
        for k, v in node.items():
            if k in _SKIP_KEYS:
                continue
            out.extend(_walk_texts(v, f"{path}.{k}" if path else k))
    elif isinstance(node, list):
        for i, v in enumerate(node):
            out.extend(_walk_texts(v, f"{path}[{i}]"))
    return out


def scan_schema(schema: dict[str, Any]) -> list[AbuseMatch]:
    """Return every forbidden term or card number found in user visible texts (F-ADM-01)."""
    matches: list[AbuseMatch] = []
    terms = _terms()
    for path, raw in _walk_texts(schema):
        norm = f" {normalize(raw)} "
        for lang, term in terms:
            if f" {term} " in norm:
                matches.append(AbuseMatch(path, term, lang))
        for candidate in _CARD.findall(raw):
            digits = re.sub(r"\D", "", candidate)
            if 13 <= len(digits) <= 19 and luhn_valid(digits):
                matches.append(AbuseMatch(path, "card_number", "any"))
    return matches


async def request_publication_review(db: AsyncSession, form_id: uuid.UUID, matches: list[AbuseMatch],
                                     message: str | None) -> PublicationReview:
    review = PublicationReview(form_id=form_id, matches={"items": [m.__dict__ for m in matches]},
                               message=message)
    db.add(review)
    await db.flush()
    return review


async def approved_review_exists(db: AsyncSession, form_id: uuid.UUID) -> bool:
    stmt = select(PublicationReview.id).where(PublicationReview.form_id == form_id,
                                              PublicationReview.status == "approved").limit(1)
    return (await db.execute(stmt)).first() is not None


async def create_report(db: AsyncSession, *, form_id: uuid.UUID, reason: str, details: str | None,
                        contact_enc: str | None, snapshot: dict[str, Any]) -> AbuseReport:
    report = AbuseReport(form_id=form_id, reason=reason, details=details, reporter_contact_enc=contact_enc,
                         snapshot=snapshot)
    db.add(report)
    await db.flush()
    return report


async def request_verification(db: AsyncSession, document_key: str, document_type: str) -> VerificationRequest:
    req = VerificationRequest(document_key=document_key, document_type=document_type)
    db.add(req)
    await db.flush()
    return req


async def latest_verification(db: AsyncSession) -> VerificationRequest | None:
    stmt = select(VerificationRequest).order_by(VerificationRequest.created_at.desc()).limit(1)
    return (await db.execute(stmt)).scalar_one_or_none()
