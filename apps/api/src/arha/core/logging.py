"""Structured JSON logs without personal data (S-16, rule 10)."""

from __future__ import annotations

import logging
import re
from typing import Any

import structlog

_EMAIL = re.compile(r"[\w.+-]+@[\w-]+\.[\w.-]+")
_PHONE = re.compile(r"\+?\d[\d\s-]{7,}\d")
_SENSITIVE_KEYS = {"email", "phone", "msisdn", "password", "token", "answers", "secret", "authorization",
                   "cookie", "pin", "code", "otp", "totp", "resume_code", "body", "payload"}


def scrub(value: Any) -> Any:
    if isinstance(value, str):
        return _PHONE.sub("[phone]", _EMAIL.sub("[email]", value))
    if isinstance(value, dict):
        return {k: ("[redacted]" if k.lower() in _SENSITIVE_KEYS else scrub(v)) for k, v in value.items()}
    if isinstance(value, list | tuple):
        return [scrub(v) for v in value]
    return value


def _pii_filter(_: Any, __: str, event_dict: dict[str, Any]) -> dict[str, Any]:
    return {k: ("[redacted]" if k.lower() in _SENSITIVE_KEYS else scrub(v)) for k, v in event_dict.items()}


def configure_logging(json_logs: bool = True) -> None:
    processors: list[Any] = [
        structlog.contextvars.merge_contextvars,
        structlog.processors.add_log_level,
        structlog.processors.TimeStamper(fmt="iso", utc=True),
        structlog.processors.format_exc_info,
        _pii_filter,
        structlog.processors.JSONRenderer() if json_logs else structlog.dev.ConsoleRenderer(),
    ]
    structlog.configure(processors=processors, wrapper_class=structlog.make_filtering_bound_logger(logging.INFO),
                        cache_logger_on_first_use=True)
