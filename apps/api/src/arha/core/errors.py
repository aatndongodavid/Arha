"""RFC 9457 problem details with stable codes and translated messages."""

from __future__ import annotations

from typing import Any

import structlog
from fastapi import FastAPI, Request
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse
from starlette.exceptions import HTTPException as StarletteHTTPException

from arha.core.messages import pick_locale, t

log = structlog.get_logger()
PROBLEM = "application/problem+json"


class AppError(Exception):
    """Business error. `code` is stable and documented; its message is translated."""

    def __init__(self, code: str, status: int = 400, *, params: dict[str, Any] | None = None,
                 extra: dict[str, Any] | None = None) -> None:
        super().__init__(code)
        self.code = code
        self.status = status
        self.params = params or {}
        self.extra = extra or {}


class NotFound(AppError):
    def __init__(self, code: str = "not_found") -> None:
        super().__init__(code, 404)


class Forbidden(AppError):
    def __init__(self, code: str = "forbidden") -> None:
        super().__init__(code, 403)


class Unauthorized(AppError):
    def __init__(self, code: str = "unauthenticated") -> None:
        super().__init__(code, 401)


class Conflict(AppError):
    def __init__(self, code: str, **extra: Any) -> None:
        super().__init__(code, 409, extra=extra)


def problem(request: Request, status: int, code: str, params: dict[str, Any] | None = None,
            extra: dict[str, Any] | None = None) -> JSONResponse:
    locale = pick_locale(request.headers.get("accept-language"))
    body: dict[str, Any] = {
        "type": f"https://docs.arha.africa/errors/{code}",
        "title": code,
        "status": status,
        "detail": t(f"error.{code}", locale, **(params or {})),
        "code": code,
    }
    if extra:
        body.update(extra)
    return JSONResponse(body, status_code=status, media_type=PROBLEM)


def install_error_handlers(app: FastAPI) -> None:
    @app.exception_handler(AppError)
    async def _app_error(request: Request, exc: AppError) -> JSONResponse:
        return problem(request, exc.status, exc.code, exc.params, exc.extra)

    @app.exception_handler(RequestValidationError)
    async def _validation(request: Request, exc: RequestValidationError) -> JSONResponse:
        # Never echo submitted values back: they may contain personal data.
        errors = [{"loc": [str(p) for p in e.get("loc", ())], "type": e.get("type")} for e in exc.errors()]
        return problem(request, 422, "validation_failed", extra={"errors": errors})

    @app.exception_handler(StarletteHTTPException)
    async def _http(request: Request, exc: StarletteHTTPException) -> JSONResponse:
        code = {404: "not_found", 405: "method_not_allowed", 401: "unauthenticated", 403: "forbidden"}.get(
            exc.status_code, "http_error")
        return problem(request, exc.status_code, code)

    @app.exception_handler(Exception)
    async def _unhandled(request: Request, exc: Exception) -> JSONResponse:
        log.exception("unhandled_error", path=request.url.path, error_type=type(exc).__name__)
        return problem(request, 500, "internal_error")
