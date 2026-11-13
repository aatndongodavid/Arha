"""Procrastinate application. Worker entry point: `procrastinate --app=arha.workers.app.worker_app worker`."""

from __future__ import annotations

import procrastinate

from arha.settings import get_settings


def _conninfo() -> str:
    return get_settings().database_platform_url.replace("postgresql+asyncpg://", "postgresql://")


worker_app = procrastinate.App(connector=procrastinate.PsycopgConnector(conninfo=_conninfo()),
                               import_paths=["arha.workers.tasks"])
