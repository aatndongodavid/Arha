"""F-EDI-02, F-EDI-03, F-EDI-07, F-LOG-03, F-ADM-01 (S-20)."""

from __future__ import annotations

import copy

from tests.conftest import create_org, publish_form, signup, simple_schema


async def _setup():  # type: ignore[no-untyped-def]
    user = await signup()
    org = await create_org(user)
    return user, org


async def test_F_EDI_02_concurrent_draft_save_is_detected() -> None:
    user, org = await _setup()
    form = (await user.post(f"/v1/orgs/{org}/forms", json={"title": "Brouillon"})).json()
    url = f"/v1/orgs/{org}/forms/{form['id']}/draft"
    first = await user.put(url, json={"schema": simple_schema(), "revision": 0})
    assert first.status_code == 200 and first.json()["draft_revision"] == 1
    stale = await user.put(url, json={"schema": simple_schema(), "revision": 0})
    assert stale.status_code == 409 and stale.json()["code"] == "form_revision_conflict"


async def test_F_EDI_02_invalid_schema_rejected_and_rich_text_sanitized() -> None:
    user, org = await _setup()
    form = (await user.post(f"/v1/orgs/{org}/forms", json={"title": "X"})).json()
    url = f"/v1/orgs/{org}/forms/{form['id']}/draft"
    bad = simple_schema()
    bad["pages"][0]["blocks"][0]["type"] = "javascript"
    assert (await user.put(url, json={"schema": bad, "revision": 0})).status_code == 422
    rich = simple_schema()
    rich["pages"][0]["blocks"].insert(0, {"id": "intro", "type": "rich_text", "content": {
        "fr": "<p>Bonjour<script>alert(1)</script><img src=x onerror=alert(1)></p>"}})
    saved = (await user.put(url, json={"schema": rich, "revision": 0})).json()
    content = saved["draft_schema"]["pages"][0]["blocks"][0]["content"]["fr"]
    assert "<script" not in content and "onerror" not in content and "Bonjour" in content


async def test_F_EDI_03_versions_are_immutable_and_restore_creates_a_draft() -> None:
    user, org = await _setup()
    schema = simple_schema()
    form = await publish_form(user, org, schema)
    base = f"/v1/orgs/{org}/forms/{form['id']}"
    detail = (await user.get(base)).json()
    changed = copy.deepcopy(schema)
    changed["pages"][0]["blocks"][0]["label"]["fr"] = "Nom complet"
    await user.put(f"{base}/draft", json={"schema": changed, "revision": detail["draft_revision"]})
    assert (await user.post(f"{base}/publish")).json()["version"] == 2
    versions = (await user.get(f"{base}/versions")).json()
    assert [v["number"] for v in versions] == [2, 1]
    v1 = next(v for v in versions if v["number"] == 1)
    v1_detail = (await user.get(f"{base}/versions/{v1['id']}")).json()
    assert v1_detail["schema"]["pages"][0]["blocks"][0]["label"]["fr"] == "Nom"
    restored = (await user.post(f"{base}/versions/{v1['id']}/restore")).json()
    assert restored["draft_schema"]["pages"][0]["blocks"][0]["label"]["fr"] == "Nom"
    assert restored["current_version"] == 2 and restored["has_unpublished_changes"] is True


async def test_F_EDI_07_twelve_templates_publishable() -> None:
    user, org = await _setup()
    templates = (await user.get("/v1/templates")).json()
    assert len(templates) == 12
    for tpl in templates:
        r = await user.post(f"/v1/orgs/{org}/forms", json={"title": tpl["title"]["fr"], "template": tpl["code"]})
        assert r.status_code == 201, tpl["code"]
        issues = (await user.post(f"/v1/orgs/{org}/forms/{r.json()['id']}/validate")).json()
        assert [i for i in issues if i["severity"] == "error"] == [], tpl["code"]


async def test_F_LOG_03_jump_loop_blocks_publication() -> None:
    user, org = await _setup()
    schema = simple_schema()
    schema["pages"].append({"id": "p2", "blocks": [{"id": "q2", "type": "short_text", "label": {"fr": "Q", "en": "Q"}}]})
    schema["rules"] = [{"id": "loop", "page": "p2", "when": {"field": "q2", "op": "not_empty"},
                        "then": [{"action": "jump_to_page", "target": "p1"}]}]
    form = (await user.post(f"/v1/orgs/{org}/forms", json={"title": "Boucle"})).json()
    await user.put(f"/v1/orgs/{org}/forms/{form['id']}/draft", json={"schema": schema, "revision": 0})
    r = await user.post(f"/v1/orgs/{org}/forms/{form['id']}/publish")
    assert r.status_code == 422 and r.json()["code"] == "form_logic_invalid"
    assert any(i["code"] == "jump_loop" for i in r.json()["issues"])


async def test_F_ADM_01_phishing_form_blocked_with_reason_and_review() -> None:
    user, org = await _setup()
    schema = simple_schema()
    schema["pages"][0]["blocks"].append({"id": "pin", "type": "short_text",
                                         "label": {"fr": "Entrez votre code PIN Orange Money", "en": "Your PIN code"}})
    form = (await user.post(f"/v1/orgs/{org}/forms", json={"title": "Bonus"})).json()
    await user.put(f"/v1/orgs/{org}/forms/{form['id']}/draft", json={"schema": schema, "revision": 0})
    r = await user.post(f"/v1/orgs/{org}/forms/{form['id']}/publish")
    assert r.status_code == 422 and r.json()["code"] == "publication_blocked"
    assert {m["term"] for m in r.json()["matches"]} >= {"code pin", "pin code"}
    assert (await user.get(f"/v1/orgs/{org}/forms/{form['id']}")).json()["publish_block_reason"] == "abuse_terms"
    r = await user.post(f"/v1/orgs/{org}/forms/{form['id']}/publication-review", json={"message": "Faux positif"})
    assert r.json()["status"] == "pending"


async def test_S_20_card_numbers_detected_with_luhn() -> None:
    from arha.modules.trust.service import scan_schema

    assert scan_schema({"x": {"fr": "Payez avec la carte 4111 1111 1111 1111"}})
    assert not scan_schema({"x": {"fr": "Commande 4111 1111 1111 1112 du client"}})
    assert scan_schema({"x": {"en": "Enter your PASSWORD here"}})
    assert scan_schema({"x": {"fr": "Votre mot de passe"}})
    assert not scan_schema({"x": {"fr": "Le passage est ouvert"}})
