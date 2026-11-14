"""Chantiers B et C (v1.2): variable names, stable choice codes, declared missing values, new blocks.

F-EDI-12, section 7 and section 8 bis of master prompt v1.2.
"""

from __future__ import annotations

import re

from tests.conftest import create_org, new_client, signup, submit

VAR_RE = re.compile(r"^[A-Za-z][A-Za-z0-9_]{0,31}$")


def t(fr: str, en: str | None = None) -> dict[str, str]:
    return {"fr": fr, "en": en or fr}


def collecte_schema() -> dict:  # type: ignore[type-arg]
    return {
        "schemaVersion": 1, "defaultLocale": "fr", "locales": ["fr", "en"],
        "settings": {"payments": {"enabled": False, "currency": "XAF", "feeBearer": "org", "provider": "fake"}},
        "variables": [], "rules": [],
        "pages": [{"id": "p1", "blocks": [
            {"id": "q1", "type": "number", "label": t("Âge de l'enquêté", "Age"), "required": True,
             "missingCodes": [{"code": 98, "label": t("Ne sait pas", "Does not know")},
                              {"code": 99, "label": t("Refus", "Refusal")}]},
            {"id": "q2", "type": "single_choice", "label": t("Sexe"), "required": True,
             "options": [{"id": "h", "label": t("Homme", "Man")}, {"id": "f", "label": t("Femme", "Woman")}]},
            {"id": "q3", "type": "multi_choice", "label": t("Sexe"),
             "options": [{"id": "a", "label": t("A")}, {"id": "b", "label": t("B")}]},
            {"id": "q4", "type": "short_text", "label": t("if")},
            {"id": "q5", "type": "likert_matrix", "label": t("Satisfaction"), "required": True,
             "rows": [{"id": "r1", "label": t("Accueil")}, {"id": "r2", "label": t("Prix")}],
             "columns": [{"id": "c1", "label": t("Pas du tout"), "code": 1}, {"id": "c2", "label": t("Moyen"), "code": 2},
                         {"id": "c3", "label": t("Tout à fait"), "code": 3}]},
            {"id": "q6", "type": "geopoint", "label": t("Position")},
            {"id": "q7", "type": "barcode", "label": t("Code du ménage")},
            {"id": "q8", "type": "photo", "label": t("Photo de la façade")},
        ]}],
    }


async def _form(schema: dict | None = None):  # type: ignore[no-untyped-def, type-arg]
    user = await signup()
    org = await create_org(user)
    form = (await user.post(f"/v1/orgs/{org}/forms", json={"title": "Enquête"})).json()
    r = await user.put(f"/v1/orgs/{org}/forms/{form['id']}/draft",
                       json={"schema": schema or collecte_schema(), "revision": form["draft_revision"]})
    assert r.status_code == 200, r.text
    return user, org, r.json()


def _blocks(form: dict) -> dict:  # type: ignore[type-arg]
    return {b["id"]: b for p in form["draft_schema"]["pages"] for b in p["blocks"]}


async def test_F_EDI_12_variable_names_are_generated_unique_and_portable() -> None:
    _, _, form = await _form()
    names = {bid: b.get("varName") for bid, b in _blocks(form).items()}
    assert all(n and VAR_RE.match(n) for n in names.values()), names
    assert len({n.lower() for n in names.values()}) == len(names)  # unique, case insensitive (SPSS)
    assert names["q1"] == "age_de_l_enquete"  # accents removed, words joined
    assert names["q2"] == "sexe" and names["q3"] == "sexe_2"
    assert names["q4"].lower() not in {"if", "in", "and", "or", "not", "all", "by", "to", "with"}  # reserved words


async def test_F_EDI_12_names_and_codes_stay_stable_and_editable() -> None:
    user, org, form = await _form()
    schema = form["draft_schema"]
    blocks = {b["id"]: b for b in schema["pages"][0]["blocks"]}
    assert [o["code"] for o in blocks["q2"]["options"]] == [1, 2]
    blocks["q1"]["label"]["fr"] = "Âge révolu"          # a new label does not rename the variable
    blocks["q2"]["varName"] = "genre"                    # a creator choice is kept
    blocks["q2"]["options"].insert(0, {"id": "x", "label": t("Autre")})  # new choice inserted first
    r = await user.put(f"/v1/orgs/{org}/forms/{form['id']}/draft", json={"schema": schema, "revision": form["draft_revision"]})
    after = _blocks(r.json())
    assert after["q1"]["varName"] == "age_de_l_enquete" and after["q2"]["varName"] == "genre"
    assert [(o["id"], o["code"]) for o in after["q2"]["options"]] == [("x", 3), ("h", 1), ("f", 2)]


async def test_F_EDI_12_invalid_or_colliding_names_block_publication() -> None:
    user, org, form = await _form()
    schema = form["draft_schema"]
    blocks = {b["id"]: b for b in schema["pages"][0]["blocks"]}
    blocks["q4"]["varName"] = "SEXE"          # duplicates q2 "sexe" for SPSS, which ignores case
    blocks["q7"]["varName"] = "sexe_2_1"      # collides with the dummy of q3 choice 1
    r = await user.put(f"/v1/orgs/{org}/forms/{form['id']}/draft", json={"schema": schema, "revision": form["draft_revision"]})
    assert r.status_code == 200
    issues = (await user.post(f"/v1/orgs/{org}/forms/{form['id']}/validate")).json()
    codes = {(i["code"], i["target"]) for i in issues if i["severity"] == "error"}
    assert ("varname_duplicate", "q4") in codes and ("varname_duplicate", "q7") in codes
    assert (await user.post(f"/v1/orgs/{org}/forms/{form['id']}/publish")).status_code == 422


async def test_F_EDI_12_missing_code_must_not_reuse_a_choice_code() -> None:
    schema = collecte_schema()
    schema["pages"][0]["blocks"][1]["missingCodes"] = [{"code": 1, "label": t("Refus")}]
    user, org, form = await _form(schema)
    issues = (await user.post(f"/v1/orgs/{org}/forms/{form['id']}/validate")).json()
    assert ("missing_code_conflict", "q2") in {(i["code"], i["target"]) for i in issues}


async def test_declared_missing_values_are_accepted_and_others_refused() -> None:
    user, org, form = await _form()
    assert (await user.post(f"/v1/orgs/{org}/forms/{form['id']}/publish")).status_code == 200
    base = {"q2": "h", "q5": {"r1": "c1", "r2": "c3"}}
    async with new_client() as c:
        ok = await submit(c, form["short_code"], {**base, "q1": {"missing": 98}})
        assert ok.status_code == 201, ok.text
        bad = await submit(c, form["short_code"], {**base, "q1": {"missing": 97}})
        assert bad.status_code == 422 and {"field": "q1", "code": "invalid_missing"} in bad.json()["errors"]


async def test_new_blocks_are_validated_by_the_server() -> None:
    user, org, form = await _form()
    await user.post(f"/v1/orgs/{org}/forms/{form['id']}/publish")
    async with new_client() as c:
        r = await submit(c, form["short_code"], {
            "q1": 30, "q2": "f", "q5": {"r1": "c2"}, "q6": {"lat": 120, "lon": 9.7}, "q7": "x" * 201})
        errors = {(e["field"], e["code"]) for e in r.json()["errors"]}
        assert errors == {("q5", "incomplete"), ("q6", "invalid_geopoint"), ("q7", "too_long")}
        r = await submit(c, form["short_code"], {"q1": 30, "q2": "f", "q5": {"r1": "c2", "r2": "c2"},
                                                 "q6": {"lat": 4.05, "lon": 9.7, "accuracy": 12}, "q7": "MEN-0042",
                                                 "q8": ["not-an-uploaded-file"]})
        assert r.status_code == 422 and r.json()["errors"] == [{"field": "_files", "code": "invalid_file"}]
