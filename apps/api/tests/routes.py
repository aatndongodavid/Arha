"""Flatten every APIRoute of the app, whatever the FastAPI router nesting."""

from __future__ import annotations

from collections.abc import Iterator
from typing import Any

from fastapi.routing import APIRoute


def iter_routes(routes: list[Any]) -> Iterator[APIRoute]:
    for r in routes:
        if isinstance(r, APIRoute):
            yield r
        elif hasattr(r, "original_router"):
            yield from iter_routes(r.original_router.routes)
        elif hasattr(r, "routes"):
            yield from iter_routes(r.routes)


def dependency_markers(route: APIRoute) -> set[str]:
    found: set[str] = set()

    def walk(dep: Any) -> None:
        call = getattr(dep, "call", None)
        for marker in ("__arha_public__", "__arha_authenticated__", "__arha_platform__", "__arha_permission__"):
            if call is not None and getattr(call, marker, None):
                found.add(marker if marker != "__arha_permission__" else f"perm:{call.__arha_permission__}")
        for sub in getattr(dep, "dependencies", []):
            walk(sub)

    walk(route.dependant)
    return found
