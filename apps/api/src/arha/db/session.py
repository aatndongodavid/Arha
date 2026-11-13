"""Database sessions with row level security context (rule 4, S-05).

Every application transaction runs as the `arha_app` role (no BYPASSRLS) and sets
`app.organization_id` and `app.user_id` with SET LOCAL semantics (set_config(..., true)).
Platform operations use the `arha_platform` role and must be journalled in audit_events.
"""

from __future__ import annotations

import uuid
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from functools import lru_cache

from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncEngine, AsyncSession, async_sessionmaker, create_async_engine

from arha.settings import get_settings


@lru_cache
def app_engine() -> AsyncEngine:
    return create_async_engine(get_settings().database_url, pool_size=10, max_overflow=10, pool_pre_ping=True)


@lru_cache
def platform_engine() -> AsyncEngine:
    return create_async_engine(get_settings().database_platform_url, pool_size=3, max_overflow=2,
                               pool_pre_ping=True)


@lru_cache
def _app_factory() -> async_sessionmaker[AsyncSession]:
    return async_sessionmaker(app_engine(), expire_on_commit=False)


@lru_cache
def _platform_factory() -> async_sessionmaker[AsyncSession]:
    return async_sessionmaker(platform_engine(), expire_on_commit=False)


async def set_org(session: AsyncSession, org_id: uuid.UUID | None) -> None:
    await session.execute(text("select set_config('app.organization_id', :v, true)"),
                          {"v": str(org_id) if org_id else ""})


async def set_user(session: AsyncSession, user_id: uuid.UUID | None) -> None:
    await session.execute(text("select set_config('app.user_id', :v, true)"),
                          {"v": str(user_id) if user_id else ""})


@asynccontextmanager
async def app_tx(org_id: uuid.UUID | None = None, user_id: uuid.UUID | None = None) -> AsyncIterator[AsyncSession]:
    async with _app_factory()() as session, session.begin():
        await set_org(session, org_id)
        await set_user(session, user_id)
        yield session


@asynccontextmanager
async def platform_tx() -> AsyncIterator[AsyncSession]:
    async with _platform_factory()() as session, session.begin():
        yield session


async def dispose_engines() -> None:
    for factory in (app_engine, platform_engine):
        if factory.cache_info().currsize:
            await factory().dispose()
            factory.cache_clear()
    _app_factory.cache_clear()
    _platform_factory.cache_clear()
