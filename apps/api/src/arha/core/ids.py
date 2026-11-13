"""Identifier helpers. All primary keys are UUIDv7."""

from __future__ import annotations

import uuid

import uuid_utils


def uuid7() -> uuid.UUID:
    return uuid.UUID(bytes=uuid_utils.uuid7().bytes)


def is_uuid7(value: uuid.UUID) -> bool:
    return value.version == 7
