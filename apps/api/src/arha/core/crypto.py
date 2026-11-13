"""Envelope encryption (S-07) and Ed25519 signing (tickets, receipts)."""

from __future__ import annotations

import base64
import json
from typing import Any

from nacl import secret, utils
from nacl.encoding import URLSafeBase64Encoder
from nacl.signing import SigningKey, VerifyKey

from arha.settings import get_settings


def _master() -> secret.SecretBox:
    key = base64.b64decode(get_settings().master_key.get_secret_value())
    return secret.SecretBox(key[:32].ljust(32, b"\0"))


def new_data_key() -> bytes:
    return utils.random(secret.SecretBox.KEY_SIZE)


def wrap_key(data_key: bytes) -> str:
    return base64.b64encode(_master().encrypt(data_key)).decode()


def unwrap_key(wrapped: str) -> bytes:
    return bytes(_master().decrypt(base64.b64decode(wrapped)))


def encrypt(plaintext: str, data_key: bytes | None = None) -> str:
    box = secret.SecretBox(data_key) if data_key else _master()
    return base64.b64encode(box.encrypt(plaintext.encode())).decode()


def decrypt(ciphertext: str, data_key: bytes | None = None) -> str:
    box = secret.SecretBox(data_key) if data_key else _master()
    return bytes(box.decrypt(base64.b64decode(ciphertext))).decode()


def _signing_key() -> SigningKey:
    seed = base64.b64decode(get_settings().ticket_signing_key.get_secret_value())
    return SigningKey(seed[:32].ljust(32, b"\0"))


def public_key_b64() -> str:
    return _signing_key().verify_key.encode(encoder=URLSafeBase64Encoder).decode().rstrip("=")


def _b64u(data: bytes) -> str:
    return base64.urlsafe_b64encode(data).decode().rstrip("=")


def _unb64u(data: str) -> bytes:
    return base64.urlsafe_b64decode(data + "=" * (-len(data) % 4))


def sign_compact(payload: dict[str, Any]) -> str:
    """Compact token: base64url(canonical json) . base64url(ed25519 signature)."""
    body = json.dumps(payload, separators=(",", ":"), sort_keys=True).encode()
    sig = _signing_key().sign(body).signature
    return f"{_b64u(body)}.{_b64u(sig)}"


def verify_compact(token: str, public_key: str | None = None) -> dict[str, Any]:
    body_b64, sig_b64 = token.split(".", 1)
    body = _unb64u(body_b64)
    vk = VerifyKey(_unb64u(public_key)) if public_key else _signing_key().verify_key
    vk.verify(body, _unb64u(sig_b64))
    result: dict[str, Any] = json.loads(body)
    return result
