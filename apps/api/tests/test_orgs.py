"""F-ORG-01, F-ORG-02, F-ORG-04."""

from __future__ import annotations

from arha.modules.messaging import service as mail
from tests.conftest import create_org, publish_form, signup, simple_schema


async def _invite(owner, org: str, email: str, role: str):  # type: ignore[no-untyped-def]
    r = await owner.post(f"/v1/orgs/{org}/invitations", json={"email": email, "role": role})
    assert r.status_code == 201, r.text
    token = [m for m in mail.OUTBOX if m.to == email and m.template == "invitation"][-1].text.split("token=")[1].split()[0]
    member = await signup(email)
    r = await member.post("/v1/invitations/accept", json={"token": token})
    assert r.status_code == 200, r.text
    return member


async def test_F_ORG_01_invitation_and_membership(owner_engine) -> None:  # type: ignore[no-untyped-def]
    from tests.conftest import set_plan

    owner = await signup()
    org = await create_org(owner)
    await set_plan(owner_engine, org, "pro")
    editor = await _invite(owner, org, "editeur@exemple.cm", "editor")
    me = (await editor.get("/v1/me")).json()
    assert [m["role"] for m in me["memberships"]] == ["editor"]
    members = (await owner.get(f"/v1/orgs/{org}/members")).json()
    assert {m["role"] for m in members} == {"owner", "editor"}


async def test_F_ORG_01_member_limit_from_plan() -> None:
    owner = await signup()
    org = await create_org(owner)  # discovery plan: 1 member
    r = await owner.post(f"/v1/orgs/{org}/invitations", json={"email": "x@exemple.cm", "role": "viewer"})
    assert r.status_code == 402 and r.json()["code"] == "member_limit_reached"


async def test_F_ORG_02_viewer_cannot_edit_or_export_unless_allowed(owner_engine) -> None:  # type: ignore[no-untyped-def]
    from tests.conftest import set_plan

    owner = await signup()
    org = await create_org(owner)
    await set_plan(owner_engine, org, "pro")
    form = await publish_form(owner, org, simple_schema())
    viewer = await _invite(owner, org, "lecteur@exemple.cm", "viewer")
    assert (await viewer.get(f"/v1/orgs/{org}/forms/{form['id']}")).status_code == 200
    r = await viewer.patch(f"/v1/orgs/{org}/forms/{form['id']}", json={"title": "Pirate"})
    assert r.status_code == 403 and r.json()["code"] == "permission_denied"
    assert (await viewer.get(f"/v1/orgs/{org}/forms/{form['id']}/export?format=csv")).status_code == 403
    assert (await owner.patch(f"/v1/orgs/{org}", json={"viewer_can_export": True})).status_code == 200
    assert (await viewer.get(f"/v1/orgs/{org}/forms/{form['id']}/export?format=csv")).status_code == 200


async def test_F_ORG_02_last_owner_cannot_be_demoted() -> None:
    owner = await signup()
    org = await create_org(owner)
    r = await owner.patch(f"/v1/orgs/{org}/members/{owner.id}", json={"role": "admin"})
    assert r.status_code == 409 and r.json()["code"] == "last_owner"


async def test_F_ORG_02_role_change_is_audited(owner_engine) -> None:  # type: ignore[no-untyped-def]
    from sqlalchemy import text

    from tests.conftest import set_plan

    owner = await signup()
    org = await create_org(owner)
    await set_plan(owner_engine, org, "pro")
    member = await _invite(owner, org, "m@exemple.cm", "viewer")
    r = await owner.patch(f"/v1/orgs/{org}/members/{member.id}", json={"role": "editor"})
    assert r.status_code == 200 and r.json()["role"] == "editor"
    async with owner_engine.begin() as conn:
        actions = (await conn.execute(text("select action from audit_events where organization_id = :o"),
                                      {"o": org})).scalars().all()
    assert "member.role_changed" in actions


async def test_F_ORG_04_folders_search_and_sort() -> None:
    owner = await signup()
    org = await create_org(owner)
    folder = (await owner.post(f"/v1/orgs/{org}/folders", json={"name": "Rentrée 2027"})).json()
    for title in ("Inscription CP", "Adhésion", "Inscription CM2"):
        await owner.post(f"/v1/orgs/{org}/forms", json={"title": title, "folder_id": folder["id"]})
    found = (await owner.get(f"/v1/orgs/{org}/forms?q=inscription&sort=title")).json()
    assert [f["title"] for f in found] == ["Inscription CM2", "Inscription CP"]
    in_folder = (await owner.get(f"/v1/orgs/{org}/forms?folder_id={folder['id']}")).json()
    assert len(in_folder) == 3
