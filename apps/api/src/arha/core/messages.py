"""Translated API messages (NF-11). Keys are stable error codes."""

from __future__ import annotations

import json
from functools import lru_cache
from pathlib import Path

from arha.settings import REPO_ROOT

SUPPORTED = ("fr", "en")


@lru_cache
def _catalog(locale: str) -> dict[str, str]:
    path: Path = REPO_ROOT / "packages" / "i18n" / "api" / f"{locale}.json"
    data: dict[str, str] = json.loads(path.read_text(encoding="utf-8"))
    return data


def pick_locale(accept_language: str | None) -> str:
    if not accept_language:
        return "fr"
    for part in accept_language.split(","):
        tag = part.split(";")[0].strip().lower()[:2]
        if tag in SUPPORTED:
            return tag
    return "fr"


def t(key: str, locale: str = "fr", **params: object) -> str:
    text = _catalog(locale).get(key) or _catalog("fr").get(key) or key
    try:
        return text.format(**params)
    except (KeyError, IndexError):
        return text


def missing_keys() -> set[str]:
    fr, en = set(_catalog("fr")), set(_catalog("en"))
    return fr ^ en
