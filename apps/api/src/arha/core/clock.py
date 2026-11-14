"""Single source of time, overridable in tests."""

from __future__ import annotations

from datetime import UTC, datetime
from zoneinfo import ZoneInfo

DOUALA = ZoneInfo("Africa/Douala")
_frozen: datetime | None = None


def now() -> datetime:
    return _frozen if _frozen is not None else datetime.now(UTC)


def freeze(at: datetime | None) -> None:
    global _frozen
    _frozen = at
