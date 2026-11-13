"""S-05: organisation B never reaches organisation A's data, on any route, and RLS holds at the database level."""

from __future__ import annotations

import re
import uuid

from sqlalchemy import text
from sqlalchemy.ext.asyncio import create_async_engine

from arha.main import app
from tests.conftest import create_org, paid_schema, publish_form, signup, submit
from tests.routes import iter_routes


async def test_S_05_every_org_route_refuses_another_org() -> None:
    a = await signup("a@exemple.cm")
    org_a = await create_org(a, "Organisation A")
    form = await publish_form(a, org_a, paid_schema())
    r = await submit(a.client, form["short_code"], {"name": "Awa", "tickets": {"std": 1}})
    sub_id = r.json()["id"]
    folder = (await a.post(f"/v1/orgs/{org_a}/folders", json={"name": "Dossier A"})).json()

    b = await signup("b@exemple.cm")
    await create_org(b, "Organisation B")

    ids = {"org_id": org_a, "form_id": form["id"], "submission_id": sub_id, "folder_id": folder["id"],
           "version_id": str(uuid.uuid4()), "invitation_id": str(uuid.uuid4()), "user_id": a.id,
           "endpoint_id": str(uuid.uuid4()), "invoice_id": str(uuid.uuid4())}
    leaks = []
    checked = 0
    for route in iter_routes(app.routes):
        if "{org_id}" not in route.path:
            continue
        path = re.sub(r"\{(\w+)\}", lambda m: ids.get(m.group(1), str(uuid.uuid4())), route.path)
        for method in route.methods or []:
            r = await b.req(method, path, json={})
            checked += 1
            if r.status_code not in (403, 404):
                leaks.append(f"{method} {route.path} -> {r.status_code}")
    assert checked > 40
    assert leaks == []


async def test_S_05_rls_blocks_rows_without_org_context() -> None:
    a = await signup()
    org_a = await create_org(a)
    await publish_form(a, org_a, paid_schema())
    engine = create_async_engine("postgresql+asyncpg://arha_app:arha_app@localhost:5432/arha_test")
    async with engine.begin() as conn:
        assert (await conn.execute(text("select count(*) from forms"))).scalar_one() == 0
        await conn.execute(text("select set_config('app.organization_id', :o, true)"), {"o": str(uuid.uuid4())})
        assert (await conn.execute(text("select count(*) from forms"))).scalar_one() == 0
        await conn.execute(text("select set_config('app.organization_id', :o, true)"), {"o": org_a})
        assert (await conn.execute(text("select count(*) from forms"))).scalar_one() == 1
        bypass = (await conn.execute(text("select rolbypassrls from pg_roles where rolname = current_user"))).scalar()
        assert bypass is False
    await engine.dispose()
