"""MSISDN hashing and masking for USSD sessions and analytics."""

from __future__ import annotations

import hashlib
import hmac
import re

from app.core.config import get_settings


def normalize_msisdn(raw: str) -> str:
    digits = re.sub(r"\D+", "", (raw or "").strip())
    if digits.startswith("254") and len(digits) == 12:
        return digits
    if digits.startswith("0") and len(digits) == 10:
        return f"254{digits[1:]}"
    if len(digits) == 9 and digits.startswith("7"):
        return f"254{digits}"
    return digits


def mask_msisdn(raw: str) -> str:
    n = normalize_msisdn(raw)
    if len(n) < 6:
        return "***"
    return f"{n[:3]}****{n[-3:]}"


def hash_msisdn(raw: str) -> str:
    settings = get_settings()
    material = (
        (getattr(settings, "ussd_hash_pepper", None) or "").strip()
        or (settings.csrf_secret or "").strip()
        or "ussd-dev-pepper"
    )
    normalized = normalize_msisdn(raw)
    return hmac.new(material.encode(), normalized.encode(), hashlib.sha256).hexdigest()
