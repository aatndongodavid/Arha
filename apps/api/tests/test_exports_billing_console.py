"""F-REP-04, F-REP-06, S-11, F-ANA-01..03, F-FAC-01..05, F-ORG-03, F-ADM-02..04, S-16."""

from __future__ import annotations

import json
from pathlib import Path

import httpx
import pyotp
import pyreadstat
import pytest
from sqlalchemy import text

from arha.modules.messaging import service as mail
from arha.modules.payments.adapters.fake import FAKE
from tests.conftest import PASSWORD, create_org, new_client, publish_form, set_plan, signup, simple_schema, submit


async def _with_responses(owner_engine, plan: str = "pro"):  # type: ignore[no-untyped-def]
    user = await signup()
    org = await create_org(user)
    await set_plan(owner_engine, org, plan)
    form = await publish_form(user, org, simple_schema())
    async with new_client() as c:
        for name, level in (("Awa", "a"), ("Ali", "b"), ("Élise", "b")):
            assert (await submit(c, form["short_code"], {"name": name, "level": level})).status_code == 201
    return user, org, form


async def test_F_REP_04_spss_and_stata_keep_labels(owner_engine, tmp_path: Path) -> None:  # type: ignore[no-untyped-def]
    user, org, form = await _with_responses(owner_engine)
    base = f"/v1/orgs/{org}/forms/{form['id']}/export"
    sav = await user.get(f"{base}?format=sav")
    assert sav.status_code == 200
    (tmp_path / "e.sav").write_bytes(sav.content)
    df, meta = pyreadstat.read_sav(str(tmp_path / "e.sav"), output_format="polars")
    assert len(df) == 3 and meta.column_names_to_labels["niveau"] == "Niveau"
    assert meta.variable_value_labels["niveau"] == {1.0: "A", 2.0: "B"}
    assert sorted(df["niveau"].to_list()) == [1.0, 2.0, 2.0]
    dta = await user.get(f"{base}?format=dta&lang=en")
    (tmp_path / "e.dta").write_bytes(dta.content)
    _, meta = pyreadstat.read_dta(str(tmp_path / "e.dta"), output_format="polars")
    assert meta.column_names_to_labels["niveau"] == "Level" and meta.variable_value_labels["niveau"] == {1: "A", 2: "B"}
    csv = await user.get(f"{base}?format=csv")
    assert "Élise" in csv.content.decode("utf-8-sig")
    xlsx = await user.get(f"{base}?format=xlsx")
    assert xlsx.content[:2] == b"PK"
    dico = (await user.get(f"{base}?format=dictionary")).content.decode("utf-8-sig")
    assert "1=A; 2=B" in dico


async def test_F_REP_04_stat_exports_need_pro_plan(owner_engine) -> None:  # type: ignore[no-untyped-def]
    user, org, form = await _with_responses(owner_engine, plan="decouverte")
    base = f"/v1/orgs/{org}/forms/{form['id']}/export"
    assert (await user.get(f"{base}?format=csv")).status_code == 200
    r = await user.get(f"{base}?format=sav")
    assert r.status_code == 402 and r.json()["code"] == "export_not_in_plan"


async def test_F_ANA_01_summary_and_F_ANA_02_funnel(owner_engine) -> None:  # type: ignore[no-untyped-def]
    user, org, form = await _with_responses(owner_engine)
    s = (await user.get(f"/v1/orgs/{org}/forms/{form['id']}/summary")).json()
    level = next(q for q in s["questions"] if q["id"] == "level")
    assert [d["count"] for d in level["data"]] == [1, 2] and level["chart"] == "bar"
    assert s["responses"] == 3 and s["funnel"]["views"] >= 3 and s["funnel"]["completes"] == 3
    assert all(q["id"] != "name" for q in s["questions"])  # identifying text never summarized


async def test_F_REP_06_webhook_signed_and_retried(owner_engine, monkeypatch) -> None:  # type: ignore[no-untyped-def]
    from arha.core import jobs
    from arha.db.session import app_tx
    from arha.modules.integrations import service as integ
    from arha.modules.integrations.models import WebhookDelivery

    async def fake_resolve(url: str) -> list[str]:
        return ["93.184.216.34"]

    monkeypatch.setattr(integ, "resolve_public", fake_resolve)
    received: list[httpx.Request] = []
    answers = iter([500, 200])

    def handler(request: httpx.Request) -> httpx.Response:
        received.append(request)
        return httpx.Response(next(answers))

    real_deliver = integ.deliver

    async def deliver_with_transport(db, delivery, **_):  # type: ignore[no-untyped-def]
        return await real_deliver(db, delivery, transport=httpx.MockTransport(handler))

    monkeypatch.setattr(integ, "deliver", deliver_with_transport)
    user = await signup()
    org = await create_org(user)
    await set_plan(owner_engine, org, "pro")
    form = await publish_form(user, org, simple_schema())
    created = (await user.post(f"/v1/orgs/{org}/webhooks", json={"url": "https://hooks.exemple.cm/arha"})).json()
    async with new_client() as c:
        await submit(c, form["short_code"], {"name": "Awa"})
    assert len(received) == 1 and jobs.SCHEDULED[0][2] == 60  # first attempt failed, retry in 60 s
    await jobs.run_scheduled()
    assert len(received) == 2
    req = received[1]
    assert integ.verify_signature(created["secret"], req.content, req.headers["Arha-Signature"])
    assert not integ.verify_signature("whsec_wrong", req.content, req.headers["Arha-Signature"])
    assert json.loads(req.content)["type"] == "submission.completed"
    log = (await user.get(f"/v1/orgs/{org}/webhooks/{created['id']}/deliveries")).json()
    assert log[0]["attempt"] == 2 and log[0]["delivered_at"] is not None
    del app_tx, WebhookDelivery


@pytest.mark.parametrize("url", [
    "http://exemple.cm/hook", "https://127.0.0.1/hook", "https://localhost/hook", "https://10.0.0.5/x",
    "https://169.254.169.254/latest/meta-data", "https://[::1]/x", "https://metadata.google.internal/x",
    "https://user:pass@exemple.cm/x", "https://192.168.1.10/x"])
async def test_S_11_ssrf_targets_are_refused(url: str, owner_engine) -> None:  # type: ignore[no-untyped-def]
    user = await signup()
    org = await create_org(user)
    await set_plan(owner_engine, org, "pro")
    r = await user.post(f"/v1/orgs/{org}/webhooks", json={"url": url})
    assert r.status_code == 422, url


async def test_F_FAC_01_subscription_by_mobile_money_invoice_and_downgrade(anon, owner_engine) -> None:  # type: ignore[no-untyped-def]
    from arha.modules.billing.tasks import renewal_cycle

    user = await signup()
    org = await create_org(user)
    plans = (await anon.get("/v1/plans")).json()
    assert plans["plans"]["pro"]["price_monthly"] == 9900 and plans["plans"]["pro"]["price_yearly"] == 99000
    r = await user.post(f"/v1/orgs/{org}/billing/subscribe", json={"plan": "pro", "period": "monthly",
                                                                   "msisdn": "+237677123456"},
                        headers={"Idempotency-Key": "sub-key-0001"})
    assert r.status_code == 201, r.text
    body = r.json()
    assert body["pioneer"] is True and body["amount"] == 7920  # 9 900 minus the 20 % Pioneer discount
    assert (await user.get(f"/v1/orgs/{org}")).json()["plan_code"] == "decouverte"  # not active before payment
    ref = next(iter(FAKE.charges))
    assert FAKE.charges[ref].connected_account_id is None
    payload = FAKE.approve(ref)
    await anon.post("/v1/webhooks/fake", content=payload, headers={"x-fake-signature": FAKE.sign(payload)})
    assert (await user.get(f"/v1/orgs/{org}")).json()["plan_code"] == "pro"
    billing = (await user.get(f"/v1/orgs/{org}/billing")).json()
    inv = billing["invoices"][0]
    assert inv["number"].startswith("ARHA-") and inv["amount"] == 7920
    pdf = await user.get(f"/v1/orgs/{org}/billing/invoices/{inv['id']}.pdf")
    assert pdf.content.startswith(b"%PDF")
    assert any(m.template == "invoice" for m in mail.OUTBOX)

    async with owner_engine.begin() as conn:  # 6 days before the end: reminder
        await conn.execute(text("update subscriptions set period_end = now() + interval '6 days'"))
    assert (await renewal_cycle())["reminded"] == 1 and any(m.template == "renewal_reminder" for m in mail.OUTBOX)
    assert (await renewal_cycle())["reminded"] == 0
    async with owner_engine.begin() as conn:  # 8 days unpaid: back to Discovery, nothing deleted
        await conn.execute(text("update subscriptions set period_end = now() - interval '8 days'"))
    assert (await renewal_cycle())["downgraded"] == 1
    assert (await user.get(f"/v1/orgs/{org}")).json()["plan_code"] == "decouverte"
    async with owner_engine.begin() as conn:
        assert (await conn.execute(text("select count(*) from invoices"))).scalar_one() == 1


async def test_F_FAC_05_prices_come_from_configuration(tmp_path: Path) -> None:
    import yaml

    from arha.core.plans import load_plans
    from arha.settings import get_settings

    raw = yaml.safe_load((get_settings().config_dir / "plans.yaml").read_text())
    raw["plans"]["pro"]["price_monthly"] = 12500
    (tmp_path / "plans.yaml").write_text(yaml.safe_dump(raw))
    assert load_plans(tmp_path / "plans.yaml").plans["pro"].price_monthly == 12500
    del raw["plans"]["decouverte"]
    (tmp_path / "bad.yaml").write_text(yaml.safe_dump(raw))
    with pytest.raises(ValueError):
        load_plans(tmp_path / "bad.yaml")


async def _admin(owner_engine):  # type: ignore[no-untyped-def]
    admin = await signup("porteur@exemple.cm")
    async with owner_engine.begin() as conn:
        await conn.execute(text("update users set is_platform_admin = true where id = :u"), {"u": admin.id})
    assert (await admin.get("/v1/admin/overview")).status_code == 403  # MFA is mandatory (S-03)
    secret = (await admin.post("/v1/me/totp/setup")).json()["secret"]
    await admin.post("/v1/me/totp/enable", json={"code": pyotp.TOTP(secret).now()})
    r = await admin.client.post("/v1/auth/login", json={"email": admin.email, "password": PASSWORD,
                                                        "totp_code": pyotp.TOTP(secret).now()})
    admin.csrf = r.json()["csrf_token"]
    return admin


async def test_F_ADM_console_reports_suspension_verification_metrics(anon, owner_engine) -> None:  # type: ignore[no-untyped-def]
    user = await signup()
    org = await create_org(user)
    form = await publish_form(user, org, simple_schema())
    assert (await user.get("/v1/admin/overview")).status_code == 404  # hidden from non admins
    await anon.post(f"/v1/public/forms/{form['short_code']}/report", json={"reason": "phishing"})
    pdf = b"%PDF-1.4 justificatif"
    r = await user.post(f"/v1/orgs/{org}/verification", data={"document_type": "rccm"},
                        files={"file": ("rccm.pdf", pdf, "application/pdf")})
    assert r.status_code == 202, r.text
    exe = await user.post(f"/v1/orgs/{org}/verification", data={"document_type": "rccm"},
                          files={"file": ("rccm.pdf", b"MZ\x90\x00 not a pdf", "application/pdf")})
    assert exe.status_code == 415  # real type checked by magic number (S-10)

    admin = await _admin(owner_engine)
    overview = (await admin.get("/v1/admin/overview")).json()
    assert overview["open_reports"] == 1 and overview["pending_verifications"] == 1
    ver = (await admin.get("/v1/admin/verifications")).json()[0]
    assert "s=" in ver["document_url"]
    await admin.post(f"/v1/admin/verifications/{ver['id']}/decision", json={"decision": "approve"})
    meta = (await anon.get(f"/v1/public/forms/{form['short_code']}")).json()
    assert meta["organization"]["verified"] is True
    badge = (await anon.get(f"/v1/public/orgs/{meta['organization']['slug']}/verification")).json()
    assert badge["verified"] is True
    report = (await admin.get("/v1/admin/reports")).json()[0]
    assert report["snapshot"]["title"] == "Gala 2027"
    await admin.post(f"/v1/admin/reports/{report['id']}/decision", json={"decision": "suspend_form", "note": "fraude"})
    assert (await anon.get(f"/v1/public/forms/{form['short_code']}")).status_code == 410
    metrics = (await admin.get("/v1/admin/metrics")).json()
    assert [t["code"] for t in metrics["thresholds"]] == ["P1", "P2", "P3", "P4"]
    async with owner_engine.begin() as conn:  # F-ADM-03: every console action is journalled
        actions = set((await conn.execute(text("select action from audit_events where action like 'platform.%'"))).scalars())
    assert {"platform.form_suspended", "platform.report_decided", "platform.verification_decided"} <= actions


async def test_S_16_audit_chain_detects_tampering(owner_engine) -> None:  # type: ignore[no-untyped-def]
    from sqlalchemy import select
    from sqlalchemy.ext.asyncio import AsyncSession

    from arha.modules.trust.models import AuditEvent
    from arha.modules.trust.service import verify_chain

    user = await signup()
    org = await create_org(user)
    await publish_form(user, org, simple_schema())
    async with AsyncSession(owner_engine) as db:
        events = list((await db.execute(select(AuditEvent).where(AuditEvent.organization_id == org).order_by(
            AuditEvent.created_at, AuditEvent.id))).scalars())
        assert len(events) >= 3 and verify_chain(events)
        events[1].metadata_ = {"tampered": True}
        assert not verify_chain(events)
        db.expunge_all()


def test_S_16_logs_never_contain_personal_data() -> None:
    from arha.core.logging import scrub

    out = scrub({"email": "awa@exemple.cm", "note": "appeler +237 677 12 34 56 ou awa@exemple.cm",
                 "answers": {"nom": "Awa"}, "nested": [{"token": "abc"}]})
    assert out == {"email": "[redacted]", "note": "appeler [phone] ou [email]", "answers": "[redacted]",
                   "nested": [{"token": "[redacted]"}]}


def test_NF_11_api_catalogs_are_complete_in_both_languages() -> None:
    from arha.core.messages import missing_keys

    assert missing_keys() == set()
