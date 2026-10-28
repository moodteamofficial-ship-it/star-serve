"""Envelope encryption for secrets stored in the database (dedicated DSNs).

Reads of already-stored plaintext are accepted only when ``require_envelope``
is false (bootstrap of legacy rows). New writes must be Fernet tokens.
"""

from __future__ import annotations

import base64
import hashlib
from urllib.parse import urlparse

from cryptography.fernet import Fernet, InvalidToken

from app.core.config import get_settings

_FERNET_PREFIX = "gAAAA"


def _fernet() -> Fernet:
    raw = (get_settings().encryption_key or "").encode("utf-8")
    digest = hashlib.sha256(raw).digest()
    return Fernet(base64.urlsafe_b64encode(digest))


def is_fernet_token(value: str | None) -> bool:
    return bool(value) and value.strip().startswith(_FERNET_PREFIX)


def encrypt_secret(value: str) -> str:
    text = (value or "").strip()
    if not text:
        return text
    if text.startswith(_FERNET_PREFIX):
        return text
    return _fernet().encrypt(text.encode("utf-8")).decode("ascii")


def decrypt_secret(value: str | None, *, require_envelope: bool = False) -> str | None:
    if not value:
        return value
    text = value.strip()
    if not text.startswith(_FERNET_PREFIX):
        if require_envelope:
            raise ValueError("Stored secret is not an encrypted envelope")
        return text
    try:
        return _fernet().decrypt(text.encode("ascii")).decode("utf-8")
    except InvalidToken as exc:
        raise ValueError("Unable to decrypt stored secret") from exc


def assert_dedicated_dsn_allowed(plaintext: str) -> str:
    """Refuse anything that is not a PostgreSQL URL on an allowlisted host."""
    text = (plaintext or "").strip()
    if not text.startswith("postgresql"):
        raise ValueError("Only PostgreSQL DSNs are supported")
    parsed = urlparse(text)
    host = (parsed.hostname or "").strip().lower()
    if not host:
        raise ValueError("Dedicated DSN is missing a host")
    settings = get_settings()
    allowed = {
        item.strip().lower()
        for item in (settings.dedicated_dsn_hosts or "").split(",")
        if item.strip()
    }
    if not allowed:
        if settings.is_production and not settings.allow_insecure_production:
            raise ValueError("DEDICATED_DSN_HOSTS must be configured in production")
        allowed = {"localhost", "127.0.0.1", "::1"}
    if host not in allowed:
        raise ValueError("Dedicated DSN host is not allowed")
    return text
