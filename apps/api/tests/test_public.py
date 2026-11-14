"""F-PUB-03..09, F-LOG-04, F-LOG-05, F-FAC-03, rule 2."""

from __future__ import annotations

from sqlalchemy import text

from arha.core.ids import uuid7
from tests.conftest import create_org, paid_schema, publish_form, set_plan, signup, simple_schema, submit


async def _form(schema=None):  # type: ignore[no-untyped-def]
    user = await signup()
    org = await create_org(user)
    form = await publish_form(user, org, schema or simple_schema())
    return user, org, form


async def test_F_PUB_04_replayed_submission_is_stored_once(anon) -> None:  # type: ignore[no-untyped-def]
    user, org, form = await _form()
    sid = str(uuid7())
    first = await submit(anon, form["short_code"], {"name": "Awa", "level": "a"}, sub_id=sid, key="replay-key-1")
    second = await submit(anon, form["short_code"], {"name": "Awa", "level": "a"}, sub_id=sid, key="replay-key-1")
    third = await submit(anon, form["short_code"], {"name": "Awa", "level": "a"}, sub_id=sid, key="other-key-22")
    assert first.status_code == 201 and second.status_code == 200 and third.status_code == 200
    page = (await user.get(f"/v1/orgs/{org}/forms/{form['id']}/submissions")).json()
    assert page["total"] == 1


async def test_rule_2_server_ignores_browser_amount_and_hidden_fields(anon) -> None:  # type: ignore[no-untyped-def]
    user, org, form = await _form(paid_schema())
    r = await submit(anon, form["short_code"], {"name": "Awa", "tickets": {"std": 2}, "amount": 1, "total": 10})
    assert r.status_code == 201 and r.json()["amount"] == 10000
    stored = (await user.get(f"/v1/orgs/{org}/forms/{form['id']}/submissions")).json()["items"][0]
    assert "amount" not in stored["answers"] and "total" not in stored["answers"]


async def test_submission_validation_errors_are_returned(anon) -> None:  # type: ignore[no-untyped-def]
    _, _, form = await _form()
    r = await submit(anon, form["short_code"], {"email": "pas-un-email"})
    assert r.status_code == 422
    assert {e["field"] for e in r.json()["errors"]} == {"name", "email"}


async def test_F_PUB_03_and_F_PUB_05_partial_save_and_resume_code(anon) -> None:  # type: ignore[no-untyped-def]
    _, _, form = await _form()
    code = form["short_code"]
    sid = str(uuid7())
    r = await submit(anon, code, {"name": "Awa"}, sub_id=sid, partial=True)
    assert r.status_code == 202
    rc = (await anon.post(f"/v1/public/forms/{code}/submissions/{sid}/resume-code")).json()["code"]
    assert len(rc) == 6 and not set(rc) & set("01OI")
    resumed = await anon.post(f"/v1/public/forms/{code}/resume", json={"code": rc})
    assert resumed.status_code == 200 and resumed.json()["answers"] == {"name": "Awa"}
    wrong = await anon.post(f"/v1/public/forms/{code}/resume", json={"code": "ZZZZZZ"})
    assert wrong.status_code == 404


async def test_F_PUB_05_resume_attempts_are_rate_limited(anon) -> None:  # type: ignore[no-untyped-def]
    _, _, form = await _form()
    codes = [(await anon.post(f"/v1/public/forms/{form['short_code']}/resume", json={"code": "ABCDEF"})).status_code
             for _ in range(6)]
    assert codes[:5] == [404] * 5 and codes[5] == 429


async def test_F_LOG_05_hidden_param_recorded_as_source(anon) -> None:  # type: ignore[no-untyped-def]
    user, org, form = await _form()
    meta = (await anon.get(f"/v1/public/forms/{form['short_code']}")).json()
    r = await anon.post(f"/v1/public/forms/{form['short_code']}/submissions", json={
        "id": str(uuid7()), "form_version_id": meta["version_id"], "answers": {"name": "Awa"},
        "hidden": {"source": "whatsapp"}}, headers={"Idempotency-Key": "hidden-key-1"})
    assert r.status_code == 201
    row = (await user.get(f"/v1/orgs/{org}/forms/{form['id']}/submissions")).json()["items"][0]
    assert row["source"] == "whatsapp"


async def test_F_PUB_06_open_graph_tags(anon) -> None:  # type: ignore[no-untyped-def]
    _, _, form = await _form()
    page = await anon.get(f"/v1/public/forms/{form['short_code']}/page")
    assert page.status_code == 200 and 'property="og:title" content="Gala 2027"' in page.text


async def test_F_PUB_09_branding_and_closed_form(anon) -> None:  # type: ignore[no-untyped-def]
    user, org, form = await _form()
    meta = (await anon.get(f"/v1/public/forms/{form['short_code']}")).json()
    assert meta["branding_required"] is True and "ref=" in meta["branding_url"]
    await user.post(f"/v1/orgs/{org}/forms/{form['id']}/close")
    meta = (await anon.get(f"/v1/public/forms/{form['short_code']}")).json()
    assert meta["status"] == "closed"
    r = await submit(anon, form["short_code"], {"name": "Tard"})
    assert r.status_code == 403 and r.json()["code"] == "form_closed"


async def test_F_PUB_08_report_reaches_console_with_snapshot(anon, owner_engine) -> None:  # type: ignore[no-untyped-def]
    _, _, form = await _form()
    r = await anon.post(f"/v1/public/forms/{form['short_code']}/report", json={"reason": "scam", "details": "Arnaque"})
    assert r.status_code == 202
    async with owner_engine.begin() as conn:
        snap = (await conn.execute(text("select snapshot from abuse_reports"))).scalar_one()
    assert snap["title"] == "Gala 2027"


async def test_F_FAC_03_quota_alert_grace_then_refusal(anon, owner_engine) -> None:  # type: ignore[no-untyped-def]
    from arha.modules.messaging import service as mail

    user, org, form = await _form()
    async with owner_engine.begin() as conn:  # 799 responses already counted this month (limit 1000)
        await conn.execute(text("insert into usage_counters (organization_id, metric, period, value) values "
                                "(:o, 'responses', to_char(now() at time zone 'Africa/Douala', 'YYYY-MM'), 799)"),
                           {"o": org})
    assert (await submit(anon, form["short_code"], {"name": "A"})).status_code == 201
    assert any(m.template == "quota_alert" for m in mail.OUTBOX)
    async with owner_engine.begin() as conn:
        await conn.execute(text("update usage_counters set value = 1000 where organization_id = :o"), {"o": org})
    assert (await submit(anon, form["short_code"], {"name": "B"})).status_code == 201  # grace period
    async with owner_engine.begin() as conn:
        await conn.execute(text("update organizations set quota_exceeded_at = now() - interval '73 hours' "
                                "where id = :o"), {"o": org})
    r = await submit(anon, form["short_code"], {"name": "C"})
    assert r.status_code == 429 and r.json()["code"] == "quota_exceeded"


async def test_F_ADM_02_suspension_takes_effect_immediately(anon, owner_engine) -> None:  # type: ignore[no-untyped-def]
    _, org, form = await _form()
    assert (await anon.get(f"/v1/public/forms/{form['short_code']}")).status_code == 200
    async with owner_engine.begin() as conn:
        await conn.execute(text("update organizations set suspended_at = now() where id = :o"), {"o": org})
    r = await anon.get(f"/v1/public/forms/{form['short_code']}")
    assert r.status_code == 410 and r.json()["code"] == "form_unavailable"


async def test_F_REP_02_status_trail_and_F_REP_07_anonymize(anon, owner_engine) -> None:  # type: ignore[no-untyped-def]
    user, org, form = await _form()
    await set_plan(owner_engine, org, "pro")
    sid = (await submit(anon, form["short_code"], {"name": "Awa", "email": "awa@exemple.cm", "level": "b"})).json()["id"]
    base = f"/v1/orgs/{org}/forms/{form['id']}/submissions"
    assert (await user.patch(f"{base}/{sid}", json={"status": "done"})).json()["status"] == "done"
    detail = (await user.get(f"{base}/{sid}")).json()
    assert detail["history"][0]["to"] == "done" and detail["history"][0]["actor_id"] == user.id
    assert (await user.post(f"{base}/anonymize", json={"ids": [sid]})).status_code == 204
    after = (await user.get(f"{base}/{sid}")).json()["submission"]
    assert after["answers"] == {"level": "b"} and after["anonymized"] is True


async def test_F_REP_01_cursor_pagination(anon) -> None:  # type: ignore[no-untyped-def]
    user, org, form = await _form()
    for i in range(7):
        await submit(anon, form["short_code"], {"name": f"P{i}"})
    base = f"/v1/orgs/{org}/forms/{form['id']}/submissions?limit=3"
    seen, cursor = [], None
    while True:
        page = (await user.get(base + (f"&cursor={cursor}" if cursor else ""))).json()
        seen += [s["id"] for s in page["items"]]
        cursor = page["next_cursor"]
        if not cursor:
            break
    assert len(seen) == len(set(seen)) == 7
    found = (await user.get(f"/v1/orgs/{org}/forms/{form['id']}/submissions?q=P3")).json()
    assert found["total"] == 1
