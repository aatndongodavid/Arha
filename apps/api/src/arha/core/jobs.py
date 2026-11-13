"""Background jobs on Procrastinate (PostgreSQL backed).

Jobs are collected during a transaction and deferred only after it commits, so a job never runs
against rolled back data. In tests (JOBS_EAGER), immediate jobs run inline after commit and
scheduled jobs are kept in SCHEDULED for the test to run explicitly.
"""

from __future__ import annotations

import os
from collections.abc import Awaitable, Callable
from typing import Any

import structlog
from sqlalchemy.ext.asyncio import AsyncSession

log = structlog.get_logger()
JobFn = Callable[..., Awaitable[None]]
REGISTRY: dict[str, JobFn] = {}
SCHEDULED: list[tuple[str, dict[str, Any], int]] = []


def eager() -> bool:
    return os.environ.get("ARHA_JOBS_EAGER") == "1"


def job(name: str, *, retry: int = 3) -> Callable[[JobFn], JobFn]:
    def decorator(fn: JobFn) -> JobFn:
        REGISTRY[name] = fn
        from arha.workers.app import worker_app

        worker_app.task(name=name, retry=retry, pass_context=False)(fn)
        return fn

    return decorator


def enqueue(db: AsyncSession, name: str, *, schedule_in: int | None = None, **kwargs: Any) -> None:
    db.info.setdefault("jobs", []).append((name, kwargs, schedule_in))


async def defer(name: str, kwargs: dict[str, Any], schedule_in: int | None = None) -> None:
    if eager():
        if schedule_in:
            SCHEDULED.append((name, kwargs, schedule_in))
            return
        await REGISTRY[name](**kwargs)
        return
    from arha.workers.app import worker_app

    task = worker_app.tasks[name]
    configured = task.configure(schedule_in={"seconds": schedule_in}) if schedule_in else task.configure()
    await configured.defer_async(**kwargs)


async def flush(db: AsyncSession) -> None:
    jobs: list[tuple[str, dict[str, Any], int | None]] = db.info.pop("jobs", [])
    for name, kwargs, schedule_in in jobs:
        try:
            await defer(name, kwargs, schedule_in)
        except Exception:  # noqa: BLE001 - a failed deferral must not fail the committed request
            log.exception("job_defer_failed", job=name)


async def run_scheduled() -> int:
    """Test helper: run every scheduled job once, in order."""
    count = 0
    while SCHEDULED:
        name, kwargs, _ = SCHEDULED.pop(0)
        await REGISTRY[name](**kwargs)
        count += 1
    return count
