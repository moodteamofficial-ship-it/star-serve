"""Kenya-oriented identity validators used across Phase 2 domains."""

import re

from app.core.exceptions import ValidationAppError

# National IDs are numeric; passports / agency refs may include letters and hyphens
# (e.g. PVT-VQ10Y8JK). Spaces are stripped; hyphens are kept.
_ID_RE = re.compile(r"^[A-Za-z0-9]+(?:-[A-Za-z0-9]+)*$")
_ID_MIN_LEN = 5
_ID_MAX_LEN = 32
_KRA_RE = re.compile(r"^[A-Za-z]\d{9}[A-Za-z]$")
_PHONE_RE = re.compile(r"^\+?[0-9]{9,15}$")
_VEHICLE_REG_RE = re.compile(r"^[A-Za-z0-9\-\s]{3,15}$")


def normalize_id_number(value: str) -> str:
    cleaned = value.strip().upper().replace(" ", "")
    cleaned = re.sub(r"-{2,}", "-", cleaned).strip("-")
    if not (
        _ID_MIN_LEN <= len(cleaned) <= _ID_MAX_LEN and _ID_RE.match(cleaned)
    ):
        raise ValidationAppError(
            "Invalid identification number",
            details=[
                {
                    "field": "id_number",
                    "msg": "Must be 5-32 letters or digits; hyphens allowed (e.g. passport)",
                }
            ],
        )
    return cleaned


def id_number_compact(value: str) -> str:
    """Hyphen-insensitive form for matching CRM / insurer ID variants."""
    return value.replace("-", "")


def id_number_lookup_variants(value: str) -> list[str]:
    """Ordered ID forms to try against the insurer (hyphenated, then compact)."""
    variants: list[str] = []
    for candidate in (value, id_number_compact(value)):
        if candidate and candidate not in variants:
            variants.append(candidate)
    return variants


def normalize_kra_pin(value: str | None) -> str | None:
    if value is None or value.strip() == "":
        return None
    cleaned = value.strip().upper()
    if not _KRA_RE.match(cleaned):
        raise ValidationAppError(
            "Invalid KRA PIN",
            details=[{"field": "kra_pin", "msg": "Expected format like A123456789B"}],
        )
    return cleaned


def normalize_phone(value: str) -> str:
    cleaned = value.strip().replace(" ", "")
    if not _PHONE_RE.match(cleaned):
        raise ValidationAppError(
            "Invalid phone number",
            details=[{"field": "phone", "msg": "Use 9-15 digits, optional leading +"}],
        )
    return cleaned


def normalize_vehicle_registration(value: str) -> str:
    cleaned = value.strip().upper()
    if not _VEHICLE_REG_RE.match(cleaned):
        raise ValidationAppError(
            "Invalid vehicle registration",
            details=[{"field": "registration", "msg": "Invalid registration format"}],
        )
    return cleaned
