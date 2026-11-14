"""Internal console (F-ADM-01..04). Platform role, MFA mandatory, every action journalled."""

from __future__ import annotations

import uuid
from datetime import timedelta
from typing import Any, Literal

from fastapi import APIRouter, Depends, Query
from pydantic import BaseModel, ConfigDict, Field
from sqlalchemy import select, text

from arha.core import clock
from arha.core.context import Ctx, platform_admin
from arha.core.errors import NotFound
from arha.core.plans import get_plans
from arha.core.storage import signed_url
from arha.db.session import platform_tx
from arha.modules.trust import service as trust
from arha.modules.trust.models import AbuseReport, PublicationReview, VerificationRequest

router = APIRouter(prefix="/v1/admin", tags=["admin"])


class DecisionIn(BaseModel):
    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)
    decision: Literal["approve", "reject", "dismiss", "suspend_form", "suspend_org"]
    note: str | None = Field(default=None, max_length=1000)


class SuspendIn(BaseModel):
    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)
    reason: str = Field(min_length=3, max_length=500)


async def _suspend(db: Any, *, form_id: uuid.UUID | None = None, org_id: uuid.UUID | None = None,
                   reason: str, actor: uuid.UUID) -> None:
    """Effective immediately: public routes read the status at every request, no cache (F-ADM-02)."""
    if form_id:
        org = (await db.execute(text("update forms set status = 'suspended' where id = :f returning organization_id"),
                                {"f": form_id})).scalar()
        await trust.audit(db, "platform.form_suspended", org_id=org, actor_id=actor, target_type="form",
                          target_id=form_id, metadata={"reason": reason})
    if org_id:
        await db.execute(text("update organizations set suspended_at = now(), suspended_reason = :r where id = :o"),
                         {"o": org_id, "r": reason})
        await trust.audit(db, "platform.org_suspended", org_id=org_id, actor_id=actor, target_type="organization",
                          target_id=org_id, metadata={"reason": reason})


@router.get("/overview")
async def overview(ctx: Ctx = Depends(platform_admin)) -> dict[str, Any]:
    async with platform_tx() as db:
        counts = (await db.execute(text(
            "select (select count(*) from abuse_reports where status = 'open'), "
            "(select count(*) from publication_reviews where status = 'open'), "
            "(select count(*) from verification_requests where status = 'pending'), "
            "(select count(*) from reconciliation_alerts where resolved_at is null)"))).one()
    return {"open_reports": counts[0], "open_reviews": counts[1], "pending_verifications": counts[2],
            "open_reconciliation_alerts": counts[3]}


@router.get("/reports")
async def reports(status: str = "open", ctx: Ctx = Depends(platform_admin)) -> list[dict[str, Any]]:
    async with platform_tx() as db:
        rows = (await db.execute(select(AbuseReport).where(AbuseReport.status == status)
                                 .order_by(AbuseReport.created_at.desc()).limit(200))).scalars()
        return [{"id": r.id, "form_id": r.form_id, "organization_id": r.organization_id, "reason": r.reason,
                 "details": r.details, "snapshot": r.snapshot, "created_at": r.created_at, "status": r.status}
                for r in rows]


@router.post("/reports/{report_id}/decision")
async def decide_report(report_id: uuid.UUID, body: DecisionIn, ctx: Ctx = Depends(platform_admin)) -> dict[str, str]:
    async with platform_tx() as db:
        report = await db.get(AbuseReport, report_id, with_for_update=True)
        if report is None:
            raise NotFound("report_not_found")
        if body.decision == "suspend_form":
            await _suspend(db, form_id=report.form_id, reason=body.note or report.reason, actor=ctx.user_id)
        elif body.decision == "suspend_org":
            await _suspend(db, org_id=report.organization_id, reason=body.note or report.reason, actor=ctx.user_id)
        report.status = "dismissed" if body.decision == "dismiss" else "actioned"
        report.decided_by, report.decided_at = ctx.user_id, clock.now()
        await trust.audit(db, "platform.report_decided", org_id=None, actor_id=ctx.user_id, target_type="report",
                          target_id=report_id, metadata={"decision": body.decision})
    return {"status": report.status}


@router.get("/reviews")
async def reviews(ctx: Ctx = Depends(platform_admin)) -> list[dict[str, Any]]:
    async with platform_tx() as db:
        rows = (await db.execute(text(
            "select r.id, r.form_id, r.organization_id, r.matches, r.message, r.created_at, f.title, f.draft_schema "
            "from publication_reviews r join forms f on f.id = r.form_id where r.status = 'open' "
            "order by r.created_at limit 200"))).mappings().all()
    return [dict(r) for r in rows]


@router.post("/reviews/{review_id}/decision")
async def decide_review(review_id: uuid.UUID, body: DecisionIn, ctx: Ctx = Depends(platform_admin)) -> dict[str, str]:
    async with platform_tx() as db:
        review = await db.get(PublicationReview, review_id, with_for_update=True)
        if review is None:
            raise NotFound()
        review.status = "approved" if body.decision == "approve" else "rejected"
        review.decided_by, review.decided_at = ctx.user_id, clock.now()
        await trust.audit(db, "platform.review_decided", org_id=review.organization_id, actor_id=ctx.user_id,
                          target_type="form", target_id=review.form_id, metadata={"decision": review.status})
    return {"status": review.status}


@router.get("/verifications")
async def verifications(ctx: Ctx = Depends(platform_admin)) -> list[dict[str, Any]]:
    async with platform_tx() as db:
        rows = (await db.execute(text(
            "select v.id, v.organization_id, o.name, v.document_type, v.document_key, v.created_at "
            "from verification_requests v join organizations o on o.id = v.organization_id "
            "where v.status = 'pending' order by v.created_at"))).mappings().all()
    return [{**{k: v for k, v in r.items() if k != "document_key"}, "document_url": signed_url(r["document_key"])}
            for r in rows]


@router.post("/verifications/{request_id}/decision")
async def decide_verification(request_id: uuid.UUID, body: DecisionIn,
                              ctx: Ctx = Depends(platform_admin)) -> dict[str, str]:
    """F-ORG-03: the porteur approves or refuses the verified badge."""
    async with platform_tx() as db:
        req = await db.get(VerificationRequest, request_id, with_for_update=True)
        if req is None:
            raise NotFound()
        req.status = "approved" if body.decision == "approve" else "rejected"
        req.note, req.decided_by, req.decided_at = body.note, ctx.user_id, clock.now()
        await db.execute(text("update organizations set verified_at = :v where id = :o"),
                         {"v": clock.now() if req.status == "approved" else None, "o": req.organization_id})
        await trust.audit(db, "platform.verification_decided", org_id=req.organization_id, actor_id=ctx.user_id,
                          target_type="organization", target_id=req.organization_id,
                          metadata={"decision": req.status})
    return {"status": req.status}


@router.post("/forms/{form_id}/suspend", status_code=204)
async def suspend_form(form_id: uuid.UUID, body: SuspendIn, ctx: Ctx = Depends(platform_admin)) -> None:
    async with platform_tx() as db:
        await _suspend(db, form_id=form_id, reason=body.reason, actor=ctx.user_id)


@router.post("/orgs/{org_id}/suspend", status_code=204)
async def suspend_org(org_id: uuid.UUID, body: SuspendIn, ctx: Ctx = Depends(platform_admin)) -> None:
    async with platform_tx() as db:
        await _suspend(db, org_id=org_id, reason=body.reason, actor=ctx.user_id)


@router.post("/orgs/{org_id}/unsuspend", status_code=204)
async def unsuspend_org(org_id: uuid.UUID, ctx: Ctx = Depends(platform_admin)) -> None:
    async with platform_tx() as db:
        await db.execute(text("update organizations set suspended_at = null, suspended_reason = null where id = :o"),
                         {"o": org_id})
        await trust.audit(db, "platform.org_unsuspended", org_id=org_id, actor_id=ctx.user_id)


@router.get("/orgs")
async def orgs(q: str | None = Query(default=None, max_length=100), ctx: Ctx = Depends(platform_admin)
               ) -> list[dict[str, Any]]:
    async with platform_tx() as db:
        rows = (await db.execute(text(
            "select id, name, slug, plan_code, verified_at, suspended_at, created_at from organizations "
            "where (:q is null or name ilike :like or slug ilike :like) order by created_at desc limit 200"),
            {"q": q, "like": f"%{q}%" if q else None})).mappings().all()
    return [dict(r) for r in rows]


@router.get("/reconciliation-alerts")
async def alerts(ctx: Ctx = Depends(platform_admin)) -> list[dict[str, Any]]:
    async with platform_tx() as db:
        rows = (await db.execute(text(
            "select id, organization_id, provider, provider_ref, payment_id, kind, details, created_at "
            "from reconciliation_alerts where resolved_at is null order by created_at desc limit 500"))
                ).mappings().all()
    return [dict(r) for r in rows]


@router.post("/reconciliation-alerts/{alert_id}/resolve", status_code=204)
async def resolve_alert(alert_id: uuid.UUID, ctx: Ctx = Depends(platform_admin)) -> None:
    async with platform_tx() as db:
        await db.execute(text("update reconciliation_alerts set resolved_at = now(), resolved_by = :u where id = :a"),
                         {"u": ctx.user_id, "a": alert_id})
        await trust.audit(db, "platform.alert_resolved", org_id=None, actor_id=ctx.user_id, target_id=alert_id)


@router.get("/metrics")
async def metrics(ctx: Ctx = Depends(platform_admin)) -> dict[str, Any]:
    """F-ADM-04: indicators of chapter 15 and investment thresholds P1 to P4 (master prompt 21)."""
    now = clock.now()
    month_start = now.astimezone(clock.DOUALA).replace(day=1, hour=0, minute=0, second=0, microsecond=0)
    plans = get_plans()
    async with platform_tx() as db:
        collected = (await db.execute(text(
            "select coalesce(sum(amount),0), coalesce(sum(platform_fee),0) from payments where status='succeeded' "
            "and purpose='submission' and updated_at >= :m"), {"m": month_start})).one()
        attempts = (await db.execute(text(
            "select count(*) filter (where status='succeeded'), count(*) filter (where status in "
            "('succeeded','failed','expired')) from payments where created_at >= :d"),
            {"d": now - timedelta(days=30)})).one()
        subs = (await db.execute(text(
            "select organization_id, billing_period, amount from subscriptions where status = 'active'"))).all()
        active_orgs = (await db.execute(text(
            "select count(*) from (select organization_id from submissions where submitted_at >= :d "
            "group by organization_id having count(*) >= 10) x"), {"d": now - timedelta(days=30)})).scalar_one()
        total_orgs = (await db.execute(text("select count(*) from organizations"))).scalar_one()
        new_orgs_60 = (await db.execute(text(
            "select count(*), count(*) filter (where plan_code <> 'decouverte') from organizations "
            "where created_at >= :d"), {"d": now - timedelta(days=60)})).one()
        churned = (await db.execute(text(
            "select count(distinct organization_id) from subscriptions where status = 'expired' "
            "and period_end >= :d"), {"d": now - timedelta(days=30)})).scalar_one()
        services_revenue = 0  # Studio services are invoiced outside the platform in V1.
    mrr = sum(a if p == "monthly" else a // plans.annual_months_charged for _, p, a in subs) + int(collected[1])
    paying = len({org for org, _, _ in subs})
    thresholds = [{"code": "P1", "rule": "10 pilotes actifs, 3 promesses d'achat, un paiement réel",
                   "reached": active_orgs >= 10 and attempts[0] >= 1},
                  {"code": "P2", "mrr": 300_000, "reached": mrr >= 300_000},
                  {"code": "P3", "mrr": 1_000_000, "reached": mrr >= 1_000_000},
                  {"code": "P4", "mrr": 3_000_000, "reached": mrr >= 3_000_000}]
    return {
        "collected_month": int(collected[0]), "platform_fees_month": int(collected[1]), "mrr": mrr,
        "paying_customers": paying, "active_organizations": active_orgs, "organizations": total_orgs,
        "conversion_60d": round(new_orgs_60[1] / new_orgs_60[0], 4) if new_orgs_60[0] else None,
        "churn_30d": round(churned / paying, 4) if paying else None,
        "payment_success_rate": round(attempts[0] / attempts[1], 4) if attempts[1] else None,
        "availability": None, "api_p95_ms": None,  # read from Prometheus and Uptime Kuma dashboards
        "services_share": round(services_revenue / mrr, 4) if mrr else None,
        "thresholds": thresholds, "generated_at": now,
    }
