"""Passwords, tokens, hashing and constant-time helpers (S-01, S-02)."""

from __future__ import annotations

import hashlib
import hmac
import secrets

import httpx
from argon2 import PasswordHasher
from argon2.exceptions import InvalidHashError, VerificationError, VerifyMismatchError

from arha.settings import get_settings

_hasher = PasswordHasher()  # argon2-cffi recommended Argon2id parameters (RFC 9106 low memory)
MIN_PASSWORD_LENGTH = 10
_UNAMBIGUOUS = "ABCDEFGHJKLMNPQRSTUVWXYZ23456789"


def hash_password(password: str) -> str:
    return _hasher.hash(password)


def verify_password(stored: str | None, password: str) -> bool:
    if not stored:
        # Spend comparable time to avoid user enumeration by timing.
        _hasher.hash(password)
        return False
    try:
        return _hasher.verify(stored, password)
    except (VerifyMismatchError, VerificationError, InvalidHashError):
        return False


def new_token(nbytes: int = 32) -> str:
    """256-bit random token, url-safe."""
    return secrets.token_urlsafe(nbytes)


def sha256_hex(value: str | bytes) -> str:
    data = value.encode() if isinstance(value, str) else value
    return hashlib.sha256(data).hexdigest()


def keyed_hash(value: str) -> str:
    """Pepper-keyed hash for identifiers such as phone numbers and IPs (never stored in clear)."""
    key = get_settings().master_key.get_secret_value().encode()
    return hmac.new(key, value.encode(), hashlib.sha256).hexdigest()


def constant_eq(a: str, b: str) -> bool:
    return hmac.compare_digest(a.encode(), b.encode())


def short_code(length: int = 6) -> str:
    return "".join(secrets.choice(_UNAMBIGUOUS) for _ in range(length))


async def is_password_pwned(password: str) -> bool:
    """k-anonymity check against Pwned Passwords: only a 5-char SHA-1 prefix leaves the server."""
    if not get_settings().pwned_passwords_check:
        return False
    # SHA-1 is imposed by the Pwned Passwords range API (S-01); it is not used to protect anything.
    # nosemgrep: python.lang.security.insecure-hash-algorithms.insecure-hash-algorithm-sha1
    digest = hashlib.sha1(password.encode(), usedforsecurity=False).hexdigest().upper()
    prefix, suffix = digest[:5], digest[5:]
    try:
        async with httpx.AsyncClient(timeout=3.0) as client:
            resp = await client.get(f"https://api.pwnedpasswords.com/range/{prefix}",
                                    headers={"Add-Padding": "true", "User-Agent": "arha-security-check"})
        resp.raise_for_status()
    except httpx.HTTPError:
        return False  # Fail open: the check is a defence in depth, not a gate on availability.
    return any(line.split(":")[0] == suffix and line.split(":")[1].strip() != "0"
               for line in resp.text.splitlines() if ":" in line)
