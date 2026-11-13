"""Test fixtures: real PostgreSQL (arha_test) with RLS, real Valkey (db 15), fake payment provider."""

from __future__ import annotations

import os

os.environ.update({
    "ARHA_ENV": "test",
    "DATABASE_URL": "postgresql+asyncpg://arha_app:arha_app@localhost:5432/arha_test",
    "DATABASE_PLATFORM_URL": "postgresql+asyncpg://arha_platform:arha_platform@localhost:5432/arha_test",
    "DATABASE_MIGRATION_URL": "postgresql+asyncpg://arha_owner:arha_owner@localhost:5432/arha_test",
    "VALKEY_URL": "redis://localhost:6379/15",
    "COOKIE_SECURE": "false",
    "PAYMENT_PROVIDER_OVERRIDE": "fake",
    "PWNED_PASSWORDS_CHECK": "false",
    "ARHA_JOBS_EAGER": "1",
    "LOCAL_FILES_DIR": "/tmp/arha-test-files",
})

import uuid
from collections.abc import AsyncIterator
from dataclasses import dataclass
from typing import Any

import pytest
from httpx import ASGITransport, AsyncClient
from sqlalchemy import text
from sqlalchemy.ext.asyncio import create_async_engine

import arha.workers.tasks  # noqa: F401  (registers jobs)
from arha.core import jobs
from arha.core.ids import uuid7
from arha.core.ratelimit import valkey
from arha.main import app
from arha.modules.messaging import service as mail
from arha.modules.payments.adapters.fake import FAKE

OWNER_URL = os.environ["DATABASE_MIGRATION_URL"]
PASSWORD = "Correct-Horse-Battery-42"


@pytest.fixture(scope="session")
async def truncate_engine() -> AsyncIterator[Any]:
    engine = create_async_engine(OWNER_URL)
    yield engine
    await engine.dispose()


@pytest.fixture(scope="session")
async def owner_engine() -> AsyncIterator[Any]:
    """Platform role (BYPASSRLS) for test setup and assertions. FORCE RLS applies even to the table owner."""
    engine = create_async_engine(os.environ["DATABASE_PLATFORM_URL"])
    yield engine
    await engine.dispose()


@pytest.fixture(autouse=True)
async def clean(truncate_engine: Any) -> AsyncIterator[None]:
    async with truncate_engine.begin() as conn:
        tables = (await conn.execute(text(
            "select tablename from pg_tables where schemaname = 'public' and tablename <> 'alembic_version'"))).scalars()
        await conn.execute(text(f"truncate {', '.join(tables)} restart identity cascade"))
    await valkey().flushdb()
    mail.OUTBOX.clear()
    jobs.SCHEDULED.clear()
    FAKE.reset()
    yield


@dataclass
class User:
    client: AsyncClient
    id: str
    email: str
    csrf: str

    async def req(self, method: str, url: str, **kw: Any) -> Any:
        headers = kw.pop("headers", {})
        if method.upper() not in ("GET", "HEAD"):
            headers.setdefault("X-CSRF-Token", self.csrf)
        return await self.client.request(method, url, headers=headers, **kw)

    async def get(self, url: str, **kw: Any) -> Any:
        return await self.req("GET", url, **kw)

    async def post(self, url: str, **kw: Any) -> Any:
        return await self.req("POST", url, **kw)

    async def put(self, url: str, **kw: Any) -> Any:
        return await self.req("PUT", url, **kw)

    async def patch(self, url: str, **kw: Any) -> Any:
        return await self.req("PATCH", url, **kw)

    async def delete(self, url: str, **kw: Any) -> Any:
        return await self.req("DELETE", url, **kw)


def new_client() -> AsyncClient:
    return AsyncClient(transport=ASGITransport(app=app), base_url="http://test",
                       headers={"Accept-Language": "fr"})


@pytest.fixture
async def anon() -> AsyncIterator[AsyncClient]:
    async with new_client() as c:
        yield c


async def signup(email: str | None = None, *, verify: bool = True) -> User:
    email = email or f"u{uuid.uuid4().hex[:10]}@exemple.cm"
    client = new_client()
    r = await client.post("/v1/auth/signup", json={"email": email, "password": PASSWORD, "display_name": "Test"})
    assert r.status_code == 201, r.text
    body = r.json()
    user = User(client=client, id=body["id"], email=email, csrf=body["csrf_token"])
    if verify:
        link = next(m for m in mail.OUTBOX if m.to == email and m.template == "verify_email")
        token = link.text.split("token=")[1].split()[0]
        r = await user.post("/v1/auth/verify-email", json={"token": token})
        assert r.status_code == 204, r.text
    return user


async def create_org(user: User, name: str = "Ecole Les Palmiers") -> str:
    r = await user.post("/v1/orgs", json={"name": name})
    assert r.status_code == 201, r.text
    return str(r.json()["id"])


async def set_plan(owner_engine: Any, org_id: str, plan: str) -> None:
    async with owner_engine.begin() as conn:
        await conn.execute(text("update organizations set plan_code = :p where id = :o"), {"p": plan, "o": org_id})


def simple_schema(**settings: Any) -> dict[str, Any]:
    schema: dict[str, Any] = {
        "schemaVersion": 1, "defaultLocale": "fr", "locales": ["fr", "en"],
        "settings": {"payments": {"enabled": False, "currency": "XAF", "feeBearer": "org", "provider": "fake"},
                     "respondentEmailField": "email", **settings},
        "variables": [], "rules": [],
        "pages": [{"id": "p1", "blocks": [
            {"id": "name", "type": "short_text", "label": {"fr": "Nom", "en": "Name"}, "required": True,
             "identifying": True},
            {"id": "email", "type": "email", "label": {"fr": "E-mail", "en": "Email"}},
            {"id": "level", "type": "single_choice", "label": {"fr": "Niveau", "en": "Level"},
             "options": [{"id": "a", "label": {"fr": "A", "en": "A"}, "code": 1},
                         {"id": "b", "label": {"fr": "B", "en": "B"}, "code": 2}]},
        ]}],
    }
    return schema


def paid_schema(fee_bearer: str = "org", quota: int | None = 150) -> dict[str, Any]:
    schema = simple_schema()
    schema["settings"]["payments"] = {"enabled": True, "currency": "XAF", "feeBearer": fee_bearer,
                                      "provider": "fake"}
    schema["pages"][0]["blocks"].append({
        "id": "tickets", "type": "ticket_choice", "label": {"fr": "Billets", "en": "Tickets"}, "required": True,
        "options": [{"id": "std", "label": {"fr": "Standard", "en": "Standard"}, "price": 5000, "quota": quota,
                     "maxQuantity": 5},
                    {"id": "vip", "label": {"fr": "VIP", "en": "VIP"}, "price": 15000, "quota": 2,
                     "maxQuantity": 2}]})
    return schema


async def publish_form(user: User, org_id: str, schema: dict[str, Any], title: str = "Gala 2027") -> dict[str, Any]:
    r = await user.post(f"/v1/orgs/{org_id}/forms", json={"title": title})
    assert r.status_code == 201, r.text
    form = r.json()
    r = await user.put(f"/v1/orgs/{org_id}/forms/{form['id']}/draft",
                       json={"schema": schema, "revision": form["draft_revision"]})
    assert r.status_code == 200, r.text
    r = await user.post(f"/v1/orgs/{org_id}/forms/{form['id']}/publish")
    assert r.status_code == 200, r.text
    return form


async def submit(client: AsyncClient, code: str, answers: dict[str, Any], *, sub_id: str | None = None,
                 key: str | None = None, partial: bool = False) -> Any:
    r = await client.get(f"/v1/public/forms/{code}")
    assert r.status_code == 200, r.text
    version_id = r.json()["version_id"]
    sid = sub_id or str(uuid7())
    return await client.post(f"/v1/public/forms/{code}/submissions",
                             json={"id": sid, "form_version_id": version_id, "answers": answers, "partial": partial},
                             headers={"Idempotency-Key": key or f"key-{sid}"})
