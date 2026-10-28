"""Helpers for Definite / provider timestamp and id normalization."""

from __future__ import annotations

from datetime import UTC, datetime
from decimal import Decimal
from typing import Any
from zoneinfo import ZoneInfo

_NAIROBI = ZoneInfo("Africa/Nairobi")


def as_optional_str(value: Any) -> str | None:
    if value is None:
        return None
    text = str(value).strip()
    return text or None


def as_optional_int(value: Any) -> int | None:
    if value is None or value == "":
        return None
    try:
        return int(str(value).strip())
    except (TypeError, ValueError):
        return None


def extract_definite_client_oid(*sources: Any) -> int | None:
    """Numeric Definite Client OID used as Policy Holder. Ignore names / blanks."""
    for source in sources:
        if source is None:
            continue
        if isinstance(source, dict):
            for key in (
                "definite_client_oid",
                "client_oid",
                "ClientOID",
                "clientOID",
                "Client",
                "PolicyHolder",
                "external_client_ref",
            ):
                oid = as_optional_int(source.get(key))
                if oid is not None:
                    return oid
            nested = source.get("customer") if isinstance(source.get("customer"), dict) else None
            if nested:
                oid = extract_definite_client_oid(nested)
                if oid is not None:
                    return oid
            continue
        oid = as_optional_int(getattr(source, "external_client_ref", source))
        if oid is not None:
            return oid
    return None


def extract_holder_email(*sources: Any) -> str | None:
    """Policy-holder email from a policy summary (incl. its ``customer`` snapshot) or a row.

    Definite LIVE refuses initiatePayment / generateCertificate without it, so the
    submit-time snapshot is a fallback when the live customer lookup comes back empty.
    """
    for source in sources:
        if source is None:
            continue
        if isinstance(source, dict):
            candidates = [source.get("customer_email"), source.get("email"), source.get("Email")]
            nested = source.get("customer")
            if isinstance(nested, dict):
                candidates.extend([nested.get("email"), nested.get("Email")])
        else:
            candidates = [getattr(source, "email", None)]
        for value in candidates:
            text = str(value or "").strip().lower()
            if "@" in text:
                return text
    return None


def definite_holder_fields(*sources: Any) -> dict[str, int]:
    """Fields Definite expects on settle / generateCertificate for the holder."""
    oid = extract_definite_client_oid(*sources)
    if oid is None:
        return {}
    return {"PolicyHolder": oid, "Client": oid, "ClientOID": oid}


def as_optional_decimal(value: Any) -> Decimal | None:
    if value is None or value == "":
        return None
    try:
        return Decimal(str(value))
    except Exception:
        return None


def parse_provider_datetime(value: Any) -> datetime | None:
    """Parse Definite datetimes (Nairobi wall clock without timezone)."""
    if value is None:
        return None
    if isinstance(value, datetime):
        if value.tzinfo is None:
            return value.replace(tzinfo=_NAIROBI).astimezone(UTC)
        return value.astimezone(UTC)
    text = str(value).strip()
    if not text:
        return None
    for fmt in (
        "%Y-%m-%d %H:%M:%S.%f",
        "%Y-%m-%d %H:%M:%S",
        "%Y-%m-%dT%H:%M:%S.%f",
        "%Y-%m-%dT%H:%M:%S",
        "%Y-%m-%d",
    ):
        try:
            naive = datetime.strptime(text.replace("Z", ""), fmt)
            return naive.replace(tzinfo=_NAIROBI).astimezone(UTC)
        except ValueError:
            continue
    try:
        parsed = datetime.fromisoformat(text.replace("Z", "+00:00"))
        if parsed.tzinfo is None:
            parsed = parsed.replace(tzinfo=_NAIROBI)
        return parsed.astimezone(UTC)
    except ValueError:
        return None
