"""F-PAY-02..09, S-19, rule 1 and rule 5."""

from __future__ import annotations

import asyncio

from sqlalchemy import text

from arha.core import jobs
from arha.modules.messaging import service as mail
from arha.modules.payments.adapters.fake import FAKE
from tests.conftest import create_org, new_client, paid_schema, publish_form, signup, submit

MSISDN = "+237677123456"


async def _paid_form(fee_bearer: str = "org", quota: int | None = 150):  # type: ignore[no-untyped-def]
    user = await signup()
    org = await create_org(user)
    form = await publish_form(user, org, paid_schema(fee_bearer, quota))
    return user, org, form


async def _pay(client, code: str, sid: str, key: str, msisdn: str = MSISDN):  # type: ignore[no-untyped-def]
    return await client.post(f"/v1/public/forms/{code}/submissions/{sid}/payments", json={"msisdn": msisdn},
                             headers={"Idempotency-Key": key})


async def _webhook(client, body: bytes, signature: str | None = None):  # type: ignore[no-untyped-def]
    return await client.post("/v1/webhooks/fake", content=body,
                             headers={"x-fake-signature": signature or FAKE.sign(body)})


async def test_F_PAY_02_end_to_end_payment_ticket_receipt(anon) -> None:  # type: ignore[no-untyped-def]
    user, org, form = await _paid_form()
    code = form["short_code"]
    sub = (await submit(anon, code, {"name": "Awa", "email": "awa@exemple.cm", "tickets": {"std": 2}})).json()
    assert sub["payment_required"] and sub["amount"] == 10000 and sub["platform_fee"] == 300  # 3 % discovery
    pay = await _pay(anon, code, sub["id"], "pay-key-0001")
    assert pay.status_code == 201 and pay.json()["status"] == "pending"
    pid = pay.json()["id"]
    ref = next(iter(FAKE.charges))
    assert FAKE.charges[ref].platform_fee == 300 and FAKE.charges[ref].amount == 10000
    assert (await _webhook(anon, FAKE.approve(ref))).status_code == 200
    status = (await anon.get(f"/v1/public/payments/{pid}")).json()
    assert status["status"] == "succeeded" and status["receipt_number"].startswith("AR-")
    token = status["access_token"]
    tickets = (await anon.get(f"/v1/public/payments/{pid}/tickets?t={token}")).json()
    assert [t["serial"] for t in tickets] == [1, 2] and "<svg" in tickets[0]["qr_svg"]
    pdf = await anon.get(f"/v1/public/payments/{pid}/receipt.pdf?t={token}")
    assert pdf.status_code == 200 and pdf.content.startswith(b"%PDF")
    assert (await anon.get(f"/v1/public/payments/{pid}/receipt.pdf?t=bad.token")).status_code == 404
    receipt = next(m for m in mail.OUTBOX if m.template == "receipt")
    assert receipt.to == "awa@exemple.cm" and len(receipt.attachments) == 2
    row = (await user.get(f"/v1/orgs/{org}/forms/{form['id']}/submissions")).json()["items"][0]
    assert row["payment_status"] == "paid"
    summary = (await user.get(f"/v1/orgs/{org}/payments/summary")).json()
    assert summary["collected"] == 10000 and summary["platform_fees"] == 300 and summary["success_rate"] == 1


async def test_F_PAY_04_double_click_never_double_charges(anon) -> None:  # type: ignore[no-untyped-def]
    _, _, form = await _paid_form()
    code = form["short_code"]
    sub = (await submit(anon, code, {"name": "Awa", "tickets": {"std": 1}})).json()
    async with new_client() as c2:
        a, b = await asyncio.gather(_pay(anon, code, sub["id"], "same-key-01"), _pay(c2, code, sub["id"], "same-key-01"))
    assert {a.status_code, b.status_code} <= {201, 409}
    assert len(FAKE.charges) == 1
    again = await _pay(anon, code, sub["id"], "same-key-01")
    assert again.status_code == 201 and len(FAKE.charges) == 1
    other = await _pay(anon, code, sub["id"], "another-key-02")
    assert other.status_code == 409 and other.json()["code"] == "payment_in_progress"
    assert len(FAKE.charges) == 1


async def test_F_PAY_04_idempotency_key_is_required(anon) -> None:  # type: ignore[no-untyped-def]
    _, _, form = await _paid_form()
    sub = (await submit(anon, form["short_code"], {"name": "Awa", "tickets": {"std": 1}})).json()
    r = await anon.post(f"/v1/public/forms/{form['short_code']}/submissions/{sub['id']}/payments",
                        json={"msisdn": MSISDN})
    assert r.status_code == 400 and r.json()["code"] == "idempotency_key_required"


async def test_F_PAY_03_webhook_signature_and_counter_verification(anon) -> None:  # type: ignore[no-untyped-def]
    _, _, form = await _paid_form()
    code = form["short_code"]
    sub = (await submit(anon, code, {"name": "Awa", "tickets": {"std": 1}})).json()
    pid = (await _pay(anon, code, sub["id"], "sig-key-0001")).json()["id"]
    ref = next(iter(FAKE.charges))
    forged = b'{"event":"payment.succeeded","data":{"ref":"%s","status":"succeeded"}}' % ref.encode()
    assert (await _webhook(anon, forged, "0" * 64)).status_code == 401
    # Correctly signed but the provider still says pending: the claim is not trusted.
    assert (await _webhook(anon, forged)).status_code == 200
    assert (await anon.get(f"/v1/public/payments/{pid}")).json()["status"] == "pending"


async def test_S_19_amount_mismatch_is_never_accepted(anon, owner_engine) -> None:  # type: ignore[no-untyped-def]
    _, _, form = await _paid_form()
    code = form["short_code"]
    sub = (await submit(anon, code, {"name": "Awa", "tickets": {"std": 1}})).json()
    pid = (await _pay(anon, code, sub["id"], "amt-key-0001")).json()["id"]
    ref = next(iter(FAKE.charges))
    await _webhook(anon, FAKE.approve(ref, amount=100))
    assert (await anon.get(f"/v1/public/payments/{pid}")).json()["status"] == "pending"
    async with owner_engine.begin() as conn:
        kinds = (await conn.execute(text("select kind from reconciliation_alerts"))).scalars().all()
    assert kinds == ["amount_mismatch"]


async def test_F_PAY_03_polling_confirms_without_webhook_then_expiry(anon, owner_engine) -> None:  # type: ignore[no-untyped-def]
    _, _, form = await _paid_form()
    code = form["short_code"]
    s1 = (await submit(anon, code, {"name": "A", "tickets": {"std": 1}})).json()
    p1 = (await _pay(anon, code, s1["id"], "poll-key-001", "+237677129999")).json()["id"]
    ref = next(iter(FAKE.charges))
    assert jobs.SCHEDULED and jobs.SCHEDULED[0][0] == "payments.poll" and jobs.SCHEDULED[0][2] == 90
    FAKE.charges[ref].status = "succeeded"  # paid, but no webhook ever arrives
    await jobs.run_scheduled()
    assert (await anon.get(f"/v1/public/payments/{p1}")).json()["status"] == "succeeded"

    s2 = (await submit(anon, code, {"name": "B", "tickets": {"vip": 2}})).json()
    p2 = (await _pay(anon, code, s2["id"], "poll-key-002")).json()["id"]
    async with owner_engine.begin() as conn:
        await conn.execute(text("update payments set expires_at = now() - interval '1 minute' where id = :p"), {"p": p2})
        assert (await conn.execute(text("select reserved from ticket_categories where option_id = 'vip'"))).scalar_one() == 2
    await jobs.run_scheduled()
    assert (await anon.get(f"/v1/public/payments/{p2}")).json()["status"] == "expired"
    async with owner_engine.begin() as conn:  # seats are released on expiry
        assert (await conn.execute(text("select reserved from ticket_categories where option_id = 'vip'"))).scalar_one() == 0


async def test_failed_charge_and_retry(anon) -> None:  # type: ignore[no-untyped-def]
    _, _, form = await _paid_form()
    code = form["short_code"]
    sub = (await submit(anon, code, {"name": "Awa", "tickets": {"std": 1}})).json()
    failed = await _pay(anon, code, sub["id"], "fail-key-001", "+237677120000")
    assert failed.json()["status"] == "failed"
    retry = await _pay(anon, code, sub["id"], "fail-key-002")
    assert retry.status_code == 201 and retry.json()["status"] == "pending"


async def test_provider_outage_reports_503_and_keeps_a_failed_payment(anon, owner_engine) -> None:  # type: ignore[no-untyped-def]
    _, _, form = await _paid_form()
    sub = (await submit(anon, form["short_code"], {"name": "Awa", "tickets": {"std": 1}})).json()
    FAKE.fail_next_initiate = True
    r = await _pay(anon, form["short_code"], sub["id"], "outage-key-1")
    assert r.status_code == 503 and r.json()["code"] == "payment_provider_unavailable"
    async with owner_engine.begin() as conn:
        assert (await conn.execute(text("select status from payments"))).scalars().all() == ["failed"]
        assert (await conn.execute(text("select sum(reserved) from ticket_categories"))).scalar_one() == 0


async def test_F_PAY_05_payer_bears_fees(anon) -> None:  # type: ignore[no-untyped-def]
    _, _, form = await _paid_form("payer")
    sub = (await submit(anon, form["short_code"], {"name": "Awa", "tickets": {"std": 2}})).json()
    assert (sub["amount"], sub["platform_fee"], sub["estimated_provider_fee"], sub["total_to_pay"]) == (
        10000, 300, 300, 10600)
    await _pay(anon, form["short_code"], sub["id"], "payer-key-01")
    assert next(iter(FAKE.charges.values())).amount == 10600


async def test_rule_3_msisdn_never_stored_in_clear(anon, owner_engine) -> None:  # type: ignore[no-untyped-def]
    _, _, form = await _paid_form()
    sub = (await submit(anon, form["short_code"], {"name": "Awa", "tickets": {"std": 1}})).json()
    await _pay(anon, form["short_code"], sub["id"], "pii-key-0001")
    async with owner_engine.begin() as conn:
        dump = (await conn.execute(text("select row_to_json(p)::text from payments p"))).scalar_one()
        audit = (await conn.execute(text("select coalesce(string_agg(metadata::text, ''), '') from audit_events"))).scalar_one()
    assert "677123456" not in dump and "677123456" not in audit


async def test_invalid_phone_is_rejected(anon) -> None:  # type: ignore[no-untyped-def]
    _, _, form = await _paid_form()
    sub = (await submit(anon, form["short_code"], {"name": "Awa", "tickets": {"std": 1}})).json()
    r = await _pay(anon, form["short_code"], sub["id"], "phone-key-01", "12345678")
    assert r.status_code == 422 and r.json()["code"] == "payment_invalid_phone"


async def test_F_PAY_07_quota_never_exceeded_with_200_concurrent_payments(owner_engine) -> None:  # type: ignore[no-untyped-def]
    _, _, form = await _paid_form(quota=150)
    code = form["short_code"]
    async with owner_engine.begin() as conn:  # this test is about the quota, not the rate limit
        pass
    from arha.core import ratelimit
    original = dict(ratelimit.LIMITS)
    ratelimit.LIMITS.update({"submission": (100000, 60), "payment_status": (100000, 60)})
    try:
        clients = [new_client() for _ in range(20)]

        async def buyer(i: int) -> str:
            c = clients[i % 20]
            sub = (await submit(c, code, {"name": f"B{i}", "tickets": {"std": 1}})).json()
            r = await _pay(c, code, sub["id"], f"quota-key-{i:04d}")
            return "sold_out" if r.status_code == 409 else r.json()["status"]

        results = await asyncio.gather(*(buyer(i) for i in range(200)))
        assert results.count("pending") == 150 and results.count("sold_out") == 50
        for ref in list(FAKE.charges):
            await _webhook(clients[0], FAKE.approve(ref))
        for c in clients:
            await c.aclose()
    finally:
        ratelimit.LIMITS.clear()
        ratelimit.LIMITS.update(original)
    async with owner_engine.begin() as conn:
        issued = (await conn.execute(text("select count(*) from tickets"))).scalar_one()
        serials = (await conn.execute(text("select count(distinct serial) from tickets"))).scalar_one()
        cat = (await conn.execute(text("select issued, reserved from ticket_categories where option_id='std'"))).one()
    assert issued == serials == 150 and tuple(cat) == (150, 0)


async def test_F_PAY_08_scan_detects_double_scan_and_offline_sync(anon) -> None:  # type: ignore[no-untyped-def]
    from arha.core.crypto import verify_compact

    user, org, form = await _paid_form()
    code = form["short_code"]
    sub = (await submit(anon, code, {"name": "Awa", "tickets": {"std": 2}})).json()
    pid = (await _pay(anon, code, sub["id"], "scan-key-0001")).json()["id"]
    await _webhook(anon, FAKE.approve(next(iter(FAKE.charges))))
    token = (await anon.get(f"/v1/public/payments/{pid}")).json()["access_token"]
    tickets = (await anon.get(f"/v1/public/payments/{pid}/tickets?t={token}")).json()
    first = await user.post(f"/v1/orgs/{org}/tickets/scan", json={"token": tickets[0]["token"]})
    assert first.json()["already_scanned"] is False
    second = await user.post(f"/v1/orgs/{org}/tickets/scan", json={"token": tickets[0]["token"]})
    assert second.json()["already_scanned"] is True
    forged = tickets[0]["token"][:-6] + "AAAAAA"
    assert (await user.post(f"/v1/orgs/{org}/tickets/scan", json={"token": forged})).status_code == 422
    bundle = (await user.get(f"/v1/orgs/{org}/forms/{form['id']}/tickets/offline-bundle")).json()
    assert len(bundle["tickets"]) == 2
    assert verify_compact(tickets[1]["token"], bundle["public_key"])["s"] == 2  # offline verification
    hashes = [{"hash": t["hash"]} for t in bundle["tickets"]]
    sync = (await user.post(f"/v1/orgs/{org}/tickets/sync", json={"scans": hashes})).json()
    assert sync["accepted"] == 1 and len(sync["duplicates"]) == 1


async def test_F_PAY_09_reconciliation_detects_injected_gaps(anon, owner_engine) -> None:  # type: ignore[no-untyped-def]
    from arha.core import clock
    from arha.modules.payments import service
    from arha.modules.payments.adapters.fake import FakeCharge

    _, _, form = await _paid_form()
    code = form["short_code"]
    sub = (await submit(anon, code, {"name": "Awa", "tickets": {"std": 1}})).json()
    await _pay(anon, code, sub["id"], "reco-key-0001")
    ref = next(iter(FAKE.charges))
    await _webhook(anon, FAKE.approve(ref))
    assert await service.reconcile() == 0
    FAKE.charges[ref].amount = 4000  # amount gap
    FAKE.charges["fake_ghost"] = FakeCharge("fake_ghost", "x", 9000, "XAF", 0, None, "succeeded", False, clock.now())
    assert await service.reconcile() == 2
    assert await service.reconcile() == 0  # alerts are not duplicated
    async with owner_engine.begin() as conn:
        kinds = sorted((await conn.execute(text("select kind from reconciliation_alerts"))).scalars().all())
    assert kinds == ["amount_mismatch", "unknown_transaction"]


async def test_payment_state_machine_refuses_forbidden_transitions() -> None:
    from arha.modules.payments.service import TRANSITIONS

    assert "pending" not in TRANSITIONS["succeeded"] and "failed" not in TRANSITIONS["succeeded"]
    assert TRANSITIONS["failed"] == set() and TRANSITIONS["refunded"] == set()
