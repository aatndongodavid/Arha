"""F-AUT-01..03, S-01..S-03."""

from __future__ import annotations

import pyotp

from arha.modules.messaging import service as mail
from tests.conftest import PASSWORD, create_org, new_client, publish_form, signup, simple_schema


async def test_F_AUT_01_signup_verify_login_and_neutral_errors() -> None:
    user = await signup("awa@exemple.cm")
    me = (await user.get("/v1/me")).json()
    assert me["email_verified"] is True
    async with new_client() as c:
        bad = await c.post("/v1/auth/login", json={"email": "awa@exemple.cm", "password": "wrong-password-1"})
        unknown = await c.post("/v1/auth/login", json={"email": "nobody@exemple.cm", "password": "wrong-password-1"})
        assert bad.status_code == unknown.status_code == 401
        assert bad.json()["code"] == unknown.json()["code"] == "invalid_credentials"
        assert bad.headers["content-type"].startswith("application/problem+json")
        ok = await c.post("/v1/auth/login", json={"email": "AWA@exemple.cm", "password": PASSWORD})
        assert ok.status_code == 200
        cookie = ok.headers["set-cookie"].lower()
        assert "httponly" in cookie and "samesite=lax" in cookie and "path=/" in cookie


async def test_F_AUT_01_magic_link_same_answer_for_unknown_email() -> None:
    await signup("ali@exemple.cm")
    async with new_client() as c:
        a = await c.post("/v1/auth/magic-link", json={"email": "ali@exemple.cm"})
        b = await c.post("/v1/auth/magic-link", json={"email": "ghost@exemple.cm"})
        assert a.status_code == b.status_code == 202 and a.json() == b.json()
        token = next(m for m in mail.OUTBOX if m.template == "magic_link").text.split("token=")[1].split()[0]
        r = await c.post("/v1/auth/magic-link/consume", json={"token": token})
        assert r.status_code == 200
        again = await c.post("/v1/auth/magic-link/consume", json={"token": token})
        assert again.status_code == 400 and again.json()["code"] == "token_invalid"


async def test_F_AUT_01_unverified_email_cannot_publish() -> None:
    user = await signup(verify=False)
    org = await create_org(user)
    r = await user.post(f"/v1/orgs/{org}/forms", json={"title": "Test"})
    form = r.json()
    r = await user.post(f"/v1/orgs/{org}/forms/{form['id']}/publish")
    assert r.status_code == 403 and r.json()["code"] == "email_not_verified"


async def test_S_01_password_policy() -> None:
    async with new_client() as c:
        r = await c.post("/v1/auth/signup", json={"email": "x@exemple.cm", "password": "short"})
        assert r.status_code == 422


async def test_S_02_csrf_required_on_unsafe_methods() -> None:
    user = await signup()
    r = await user.client.post("/v1/orgs", json={"name": "Sans jeton"})
    assert r.status_code == 403 and r.json()["code"] == "csrf_failed"
    r = await user.post("/v1/orgs", json={"name": "Avec jeton"})
    assert r.status_code == 201


async def test_F_AUT_03_session_revocation_is_immediate() -> None:
    user = await signup("multi@exemple.cm")
    async with new_client() as other:
        r = await other.post("/v1/auth/login", json={"email": "multi@exemple.cm", "password": PASSWORD})
        assert r.status_code == 200
        sessions = (await user.get("/v1/me/sessions")).json()
        assert len(sessions) == 2
        target = next(s for s in sessions if not s["current"])
        assert (await user.delete(f"/v1/me/sessions/{target['id']}")).status_code == 204
        assert (await other.get("/v1/me")).status_code == 401


async def test_F_AUT_02_totp_enable_and_login() -> None:
    user = await signup("mfa@exemple.cm")
    setup = (await user.post("/v1/me/totp/setup")).json()
    totp = pyotp.TOTP(setup["secret"])
    r = await user.post("/v1/me/totp/enable", json={"code": totp.now()})
    assert r.status_code == 200 and len(r.json()["backup_codes"]) == 10
    backup = r.json()["backup_codes"][0]
    async with new_client() as c:
        r = await c.post("/v1/auth/login", json={"email": "mfa@exemple.cm", "password": PASSWORD})
        assert r.status_code == 401 and r.json()["code"] == "mfa_code_required"
        r = await c.post("/v1/auth/login", json={"email": "mfa@exemple.cm", "password": PASSWORD,
                                                 "totp_code": backup})
        assert r.status_code == 200 and r.json()["mfa_passed"] is True
        r = await c.post("/v1/auth/login", json={"email": "mfa@exemple.cm", "password": PASSWORD,
                                                 "totp_code": backup})
        assert r.status_code == 401  # backup codes are single use


async def test_S_03_mfa_required_for_equipe_owner(owner_engine) -> None:  # type: ignore[no-untyped-def]
    from tests.conftest import set_plan

    user = await signup()
    org = await create_org(user)
    await set_plan(owner_engine, org, "equipe")
    r = await user.get(f"/v1/orgs/{org}")
    assert r.status_code == 403 and r.json()["code"] == "mfa_required"


async def test_publish_after_verification_works() -> None:
    user = await signup()
    org = await create_org(user)
    form = await publish_form(user, org, simple_schema())
    assert form["short_code"]
