"""S-04: every route declares a permission, an authenticated user requirement, the platform console guard,
or is explicitly public. Public routes are an explicit whitelist reviewed in code review."""

from __future__ import annotations

from arha.main import app
from tests.routes import dependency_markers, iter_routes

FRAMEWORK = {"/openapi.json", "/docs", "/docs/oauth2-redirect", "/redoc"}
PUBLIC_WHITELIST = {
    "/healthz", "/metrics", "/v1/plans", "/v1/public/config", "/files/{key:path}",
    "/v1/auth/signup", "/v1/auth/login", "/v1/auth/verify-email", "/v1/auth/magic-link",
    "/v1/auth/magic-link/consume", "/v1/auth/password-reset", "/v1/auth/password-reset/confirm",
    "/v1/auth/google/start", "/v1/auth/google/callback",
    "/v1/public/forms/{code}", "/v1/public/forms/{code}/page", "/v1/public/forms/{code}/submissions",
    "/v1/public/forms/{code}/submissions/{submission_id}/resume-code", "/v1/public/forms/{code}/resume",
    "/v1/public/forms/{code}/events", "/v1/public/forms/{code}/report", "/v1/public/forms/{code}/files",
    "/v1/public/orgs/{slug}/verification", "/v1/public/forms/{code}/submissions/{submission_id}/payments",
    "/v1/public/payments/{payment_id}", "/v1/public/payments/{payment_id}/receipt.pdf",
    "/v1/public/payments/{payment_id}/tickets", "/v1/webhooks/{provider}",
}


def test_S_04_every_route_has_permission_or_is_whitelisted() -> None:
    problems = []
    routes = list(iter_routes(app.routes))
    assert len(routes) > 80
    for route in routes:
        if route.path in FRAMEWORK:
            continue
        markers = dependency_markers(route)
        if not markers:
            problems.append(f"{route.methods} {route.path}: no guard")
        elif "__arha_public__" in markers and route.path not in PUBLIC_WHITELIST:
            problems.append(f"{route.methods} {route.path}: public but not whitelisted")
        elif route.path.startswith("/v1/admin"):
            if "__arha_platform__" not in markers:
                problems.append(f"{route.methods} {route.path}: console route without platform guard")
        elif "/orgs/{org_id}" in route.path and not any(m.startswith("perm:") for m in markers):
            problems.append(f"{route.methods} {route.path}: organisation route without permission")
    assert problems == []


def test_S_04_whitelist_has_no_stale_entries() -> None:
    paths = {r.path for r in iter_routes(app.routes)}
    assert paths >= PUBLIC_WHITELIST
