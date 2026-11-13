"""FastAPI application factory."""

from __future__ import annotations

from collections.abc import AsyncIterator, Awaitable, Callable
from contextlib import asynccontextmanager

import structlog
from fastapi import FastAPI, Request, Response
from fastapi.middleware.cors import CORSMiddleware
from prometheus_client import CONTENT_TYPE_LATEST, Counter, Histogram, generate_latest
from sqlalchemy import text

from arha.core.context import Ctx, public_route
from arha.core.errors import install_error_handlers
from arha.core.ids import uuid7
from arha.core.logging import configure_logging
from arha.core.plans import get_countries, get_plans
from arha.db.session import dispose_engines
from arha.settings import get_settings

REQUESTS = Counter("arha_http_requests_total", "HTTP requests", ["method", "route", "status"])
LATENCY = Histogram("arha_http_request_seconds", "HTTP latency", ["route"])


@asynccontextmanager
async def lifespan(_: FastAPI) -> AsyncIterator[None]:
    get_plans()  # invalid config/plans.yaml prevents startup (section 11)
    get_countries()
    yield
    await dispose_engines()


def create_app() -> FastAPI:
    settings = get_settings()
    configure_logging(json_logs=not settings.is_dev)
    app = FastAPI(title="Arha API", version="1.0.0", lifespan=lifespan,
                  docs_url="/docs" if settings.is_dev else None, redoc_url=None,
                  openapi_url="/openapi.json" if settings.is_dev else None)
    install_error_handlers(app)
    app.add_middleware(CORSMiddleware, allow_origins=[settings.arha_app_url, settings.arha_forms_url],
                       allow_credentials=True, allow_methods=["GET", "POST", "PATCH", "PUT", "DELETE"],
                       allow_headers=["content-type", "x-csrf-token", "idempotency-key", "accept-language"])

    @app.middleware("http")
    async def security_headers(request: Request, call_next: Callable[[Request], Awaitable[Response]]) -> Response:
        request_id = request.headers.get("x-request-id") or uuid7().hex
        structlog.contextvars.bind_contextvars(request_id=request_id)
        route = request.scope.get("route")
        with LATENCY.labels(getattr(route, "path", "unmatched")).time():
            response = await call_next(request)
        route = request.scope.get("route")
        REQUESTS.labels(request.method, getattr(route, "path", "unmatched"), response.status_code).inc()
        response.headers["X-Request-Id"] = request_id
        response.headers["X-Content-Type-Options"] = "nosniff"
        response.headers["Referrer-Policy"] = "strict-origin-when-cross-origin"
        response.headers.setdefault("Content-Security-Policy", "default-src 'none'; frame-ancestors 'none'")
        response.headers["Permissions-Policy"] = "camera=(), microphone=(), geolocation=()"
        if not settings.is_dev:
            response.headers["Strict-Transport-Security"] = "max-age=31536000; includeSubDomains; preload"
        if request.url.path.startswith(("/v1/auth", "/v1/me", "/v1/orgs", "/v1/admin")):
            response.headers["Cache-Control"] = "no-store"
        structlog.contextvars.unbind_contextvars("request_id")
        return response

    from arha.modules.analytics.router import router as analytics_router
    from arha.modules.billing.router import router as billing_router
    from arha.modules.forms.router import router as forms_router
    from arha.modules.identity.router import router as identity_router
    from arha.modules.integrations.router import router as integrations_router
    from arha.modules.orgs.router import router as orgs_router
    from arha.modules.payments.router import router as payments_router
    from arha.modules.submissions.public_router import files_router
    from arha.modules.submissions.public_router import router as public_router
    from arha.modules.submissions.router import router as submissions_router
    from arha.modules.trust.router import router as trust_router

    for r in (identity_router, orgs_router, forms_router, submissions_router, public_router, payments_router,
              billing_router, analytics_router, integrations_router, trust_router, files_router):
        app.include_router(r)

    @app.get("/healthz", tags=["ops"])
    async def health(ctx: Ctx = Depends_public()) -> dict[str, str]:
        await ctx.db.execute(text("select 1"))
        return {"status": "ok"}

    @app.get("/metrics", tags=["ops"], include_in_schema=False)
    async def metrics(ctx: Ctx = Depends_public()) -> Response:
        # Exposed on the internal network only; Caddy does not route /metrics publicly.
        return Response(generate_latest(), media_type=CONTENT_TYPE_LATEST)

    return app


def Depends_public() -> Ctx:
    from fastapi import Depends

    return Depends(public_route)  # type: ignore[no-any-return]


app = create_app()
