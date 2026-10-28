"""Cryptographic verification for Definite and payout callbacks."""

from __future__ import annotations

import hashlib
import hmac
import json
import time
from typing import Any

from app.core.config import get_settings
from app.core.exceptions import AuthenticationError, ValidationAppError

_MAX_SKEW_SECONDS = 300


def _secret() -> str:
    settings = get_settings()
    secret = (getattr(settings, "claims_webhook_hmac_secret", "") or "").strip()
    if not secret:
        if settings.is_production and not settings.local_insecure_override:
            raise AuthenticationError("Claims webhook signing secret is not configured")
        secret = (settings.csrf_secret or "change-me-csrf-dev-only").strip()
    return secret


def sign_payload(payload: bytes, *, timestamp: str, nonce: str) -> str:
    message = f"{timestamp}.{nonce}.".encode("utf-8") + payload
    return hmac.new(_secret().encode("utf-8"), message, hashlib.sha256).hexdigest()


def verify_signed_callback(
    *,
    payload: bytes,
    signature: str | None,
    timestamp: str | None,
    nonce: str | None,
) -> dict[str, Any]:
    if not signature or not timestamp or not nonce:
        raise AuthenticationError("Signed callback headers are required")
    if len(nonce) < 8 or len(nonce) > 128:
        raise AuthenticationError("Invalid callback nonce")
    try:
        ts = int(timestamp)
    except ValueError as exc:
        raise AuthenticationError("Invalid callback timestamp") from exc
    now = int(time.time())
    window = int(getattr(get_settings(), "claims_webhook_timestamp_window_seconds", _MAX_SKEW_SECONDS))
    if abs(now - ts) > window:
        raise AuthenticationError("Callback timestamp is outside the accepted window")
    expected = sign_payload(payload, timestamp=timestamp, nonce=nonce)
    if not hmac.compare_digest(expected, signature.strip().lower()):
        raise AuthenticationError("Callback signature is invalid")
    try:
        body = json.loads(payload.decode("utf-8"))
    except (UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise ValidationAppError("Callback payload is not valid JSON") from exc
    if not isinstance(body, dict):
        raise ValidationAppError("Callback payload must be an object")
    return body


def payload_hash(payload: bytes) -> str:
    return hashlib.sha256(payload).hexdigest()
