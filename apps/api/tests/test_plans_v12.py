"""Chantier A (cahier des charges v1.2): offers, Pass Mémoire, commission by plan, exports by plan.

F-FAC-01, F-FAC-03, F-FAC-05, F-FAC-06, rules E-02 and E-04, master prompt section 11.
"""

from __future__ import annotations

from sqlalchemy import text

from arha.core.plans import get_plans
from arha.modules.payments.adapters.fake import FAKE
from tests.conftest import create_org, new_client, paid_schema, publish_form, set_plan, signup, simple_schema, submit


def test_F_FAC_05_grid_v12_is_loaded_from_configuration() -> None:
    cfg = get_plans()
    assert list(cfg.plans) == ["decouverte", "pass_memoire", "pro", "equipe", "terrain", "institution"]
    assert cfg.responses_limit("decouverte") == (500, "month")
    assert cfg.responses_limit("pass_memoire") == (3000, "total")
    assert cfg.plans["pass_memoire"].price_once == 5000 and cfg.plans["pass_memoire"].duration_days == 120
    assert cfg.plans["pass_memoire"].auto_renew is False
    assert [cfg.payment_fee_bps(p) for p in ("decouverte", "pass_memoire", "pro", "equipe", "terrain", "institution")] \
        == [300, 300, 150, 100, 100, 50]
    assert cfg.exports_of("decouverte") == {"csv", "xlsx"}
    assert cfg.exports_of("equipe") == {"csv", "xlsx", "sav", "dta", "r", "codebook"}  # inherited from pro
    assert "mfa_required_owner" in cfg.features_of("terrain")
    assert cfg.limit("equipe", "reviewers") is None  # "unlimited", inherited from pro
    assert cfg.pioneer.plans == ["pro", "equipe", "terrain"]
    assert cfg.studies["turnkey_survey_from"].upfront_pct == 50


async def test_F_FAC_05_exports_follow_the_plan(owner_engine) -> None:  # type: ignore[no-untyped-def]
    user = await signup()
    org = await create_org(user)
    form = await publish_form(user, org, simple_schema())
    async with new_client() as c:
        await submit(c, form["short_code"], {"name": "Awa"})
    base = f"/v1/orgs/{org}/forms/{form['id']}/export"
    assert (await user.get(f"{base}?format=xlsx")).status_code == 200
    r = await user.get(f"{base}?format=sav")
    assert r.status_code == 402 and r.json()["code"] == "export_not_in_plan"
    await set_plan(owner_engine, org, "pass_memoire")
    assert (await user.get(f"{base}?format=sav")).status_code == 200


async def test_F_FAC_06_pass_memoire_purchase_activation_and_expiry(anon, owner_engine) -> None:  # type: ignore[no-untyped-def]
    from arha.modules.billing.tasks import renewal_cycle

    user = await signup()
    org = await create_org(user)
    r = await user.post(f"/v1/orgs/{org}/billing/pass", json={
        "institution": "Université de Douala", "level": "master", "msisdn": "+237677123456"},
        headers={"Idempotency-Key": "pass-key-0001"})
    assert r.status_code == 201, r.text
    assert r.json()["amount"] == 5000
    ref = next(iter(FAKE.charges))
    assert FAKE.charges[ref].connected_account_id is None  # Arha's own merchant account (section 9.0)
    body = FAKE.approve(ref)
    await anon.post("/v1/webhooks/fake", content=body, headers={"x-fake-signature": FAKE.sign(body)})
    assert (await user.get(f"/v1/orgs/{org}")).json()["plan_code"] == "pass_memoire"
    billing = (await user.get(f"/v1/orgs/{org}/billing")).json()
    assert billing["pass"]["institution"] == "Université de Douala"
    assert billing["usage"]["limit"] == 3000 and billing["usage"]["period"] == "total"
    assert billing["invoices"][0]["amount"] == 5000
    async with owner_engine.begin() as conn:
        days = (await conn.execute(text("select extract(day from ends_at - starts_at) from student_passes"))).scalar()
    assert int(days) == 120
    # No automatic renewal (E-04, F-FAC-06): after expiry the organisation returns to Découverte, no data deleted.
    async with owner_engine.begin() as conn:
        await conn.execute(text("update student_passes set ends_at = now() - interval '1 minute'"))
    assert (await renewal_cycle())["passes_expired"] == 1
    assert (await user.get(f"/v1/orgs/{org}")).json()["plan_code"] == "decouverte"
    assert len(FAKE.charges) == 1


async def test_F_FAC_06_pass_requires_institution_and_level() -> None:
    user = await signup()
    org = await create_org(user)
    r = await user.post(f"/v1/orgs/{org}/billing/pass", json={"msisdn": "+237677123456"},
                        headers={"Idempotency-Key": "pass-key-0002"})
    assert r.status_code == 422


async def test_F_FAC_03_pass_quota_is_a_total_not_a_monthly_quota(anon, owner_engine) -> None:  # type: ignore[no-untyped-def]
    user = await signup()
    org = await create_org(user)
    await set_plan(owner_engine, org, "pass_memoire")
    form = await publish_form(user, org, simple_schema())
    async with owner_engine.begin() as conn:
        await conn.execute(text("insert into usage_counters (organization_id, metric, period, value) values "
                                "(:o, 'responses', 'total', 2999)"), {"o": org})
    assert (await submit(anon, form["short_code"], {"name": "A"})).status_code == 201
    billing = (await user.get(f"/v1/orgs/{org}/billing")).json()
    assert billing["usage"]["responses"] == 3000


async def test_commission_follows_the_plan_from_the_next_payment(anon, owner_engine) -> None:  # type: ignore[no-untyped-def]
    user = await signup()
    org = await create_org(user)
    form = await publish_form(user, org, paid_schema())
    first = (await submit(anon, form["short_code"], {"name": "A", "tickets": {"std": 2}})).json()
    assert first["platform_fee"] == 300  # 3 % on Découverte
    await set_plan(owner_engine, org, "pro")
    second = (await submit(anon, form["short_code"], {"name": "B", "tickets": {"std": 2}})).json()
    assert second["platform_fee"] == 150  # 1.5 % on Pro


async def test_E_02_pioneer_only_on_listed_plans_and_no_other_discount(owner_engine) -> None:  # type: ignore[no-untyped-def]
    from arha.modules.billing.service import plan_price

    class Org:
        is_nonprofit = True
        verified_at = True

    assert plan_price(Org(), "pro", "monthly", pioneer_available=True) == (7920, 2000, True)
    assert plan_price(Org(), "pro", "monthly", pioneer_available=False) == (9900, 0, False)  # no nonprofit discount
    assert plan_price(Org(), "equipe", "yearly", pioneer_available=False)[0] == 299000


def test_F_FAC_05_inconsistent_configuration_prevents_startup(tmp_path) -> None:  # type: ignore[no-untyped-def]
    import pytest
    import yaml

    from arha.core.plans import load_plans
    from arha.settings import get_settings

    raw = yaml.safe_load((get_settings().config_dir / "plans.yaml").read_text())
    raw["plans"]["pro"]["exports"] = ["csv", "pdf_magic"]
    (tmp_path / "p.yaml").write_text(yaml.safe_dump(raw))
    with pytest.raises(ValueError):
        load_plans(tmp_path / "p.yaml")
    raw = yaml.safe_load((get_settings().config_dir / "plans.yaml").read_text())
    raw["pioneer"]["plans"] = ["pro", "ghost"]
    (tmp_path / "q.yaml").write_text(yaml.safe_dump(raw))
    with pytest.raises(ValueError):
        load_plans(tmp_path / "q.yaml")


