"""Private file storage with short-lived signed URLs (S-10).

LocalStorage serves dev, test and the single-server beta. An S3 compatible adapter plugs in behind
the same interface (VERIFY: provider endpoint and signature version before enabling it).
"""

from __future__ import annotations

import hashlib
import hmac
import time
from pathlib import Path
from typing import Protocol

from arha.core.errors import AppError
from arha.settings import get_settings

SIGNED_URL_SECONDS = 300

# Magic numbers for the allowed upload types.
_SIGNATURES: list[tuple[bytes, str]] = [
    (b"%PDF-", "application/pdf"),
    (b"\x89PNG\r\n\x1a\n", "image/png"),
    (b"\xff\xd8\xff", "image/jpeg"),
    (b"RIFF", "image/webp"),
    (b"PK\x03\x04", "application/zip"),
]


def sniff(data: bytes) -> str | None:
    for magic, mime in _SIGNATURES:
        if data.startswith(magic):
            if mime == "image/webp" and data[8:12] != b"WEBP":
                continue
            return mime
    return None


class Storage(Protocol):
    def put(self, key: str, data: bytes) -> None: ...
    def get(self, key: str) -> bytes: ...
    def delete(self, key: str) -> None: ...


class LocalStorage:
    def __init__(self, root: Path) -> None:
        self.root = root
        root.mkdir(parents=True, exist_ok=True)

    def _path(self, key: str) -> Path:
        if ".." in key or key.startswith("/"):
            raise AppError("invalid_file_key", 400)
        return self.root / key

    def put(self, key: str, data: bytes) -> None:
        path = self._path(key)
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(data)

    def get(self, key: str) -> bytes:
        try:
            return self._path(key).read_bytes()
        except FileNotFoundError as exc:
            raise AppError("not_found", 404) from exc

    def delete(self, key: str) -> None:
        self._path(key).unlink(missing_ok=True)


def storage() -> Storage:
    return LocalStorage(get_settings().local_files_dir)


def _sig(key: str, expires: int) -> str:
    secret = get_settings().master_key.get_secret_value().encode()
    return hmac.new(secret, f"{key}:{expires}".encode(), hashlib.sha256).hexdigest()


def signed_url(key: str) -> str:
    expires = int(time.time()) + SIGNED_URL_SECONDS
    return f"{get_settings().arha_files_url}/{key}?e={expires}&s={_sig(key, expires)}"


def check_signature(key: str, expires: int, signature: str) -> bool:
    return expires >= int(time.time()) and hmac.compare_digest(_sig(key, expires), signature)
