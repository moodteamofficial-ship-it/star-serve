"""Insurance provider policy helpers (env-aware enforcement).

This module owns the single interpretation of the insurer's double-insurance
response. Two independent parsers previously disagreed — the issuance wizard read
only the top level of the payload while the proposals path unwrapped ``data`` —
so the same "detected" answer could block one route and sail through the other.
"""

from __future__ import annotations

from typing import Any, Literal

from app.core.config import Settings, get_settings

DoubleInsuranceVerdict = Literal["CLEAR", "DETECTED", "UNKNOWN"]

# Flags the insurer has used for "this vehicle already has cover".
_FLAG_KEYS = (
    "hasDoubleInsurance",
    "hasdoubleinsurance",
    "has_double_insurance",
    "doubleInsurance",
    "isDoubleInsured",
    "exists",
    "found",
)
_STATUS_KEYS = ("status", "result", "Status", "Result")
_CLEAR_STATUSES = {"CLEAR", "OK", "NONE", "NOT_FOUND", "NOTFOUND", "NO", "FALSE", "0"}
_DETECTED_STATUSES = {
    "DETECTED",
    "EXISTS",
    "FOUND",
    "FAIL",
    "FAILED",
    "ACTIVE",
    "TRUE",
    "YES",
    "1",
}
_TRUE_WORDS = {"true", "1", "yes", "y", "detected", "found", "exists", "active"}
_FALSE_WORDS = {"false", "0", "no", "n", "none", "clear", "not_found", "notfound", ""}


def should_enforce_double_insurance(settings: Settings | None = None) -> bool:
    """Block issuance on double insurance in LIVE; soft-check on UAT/dev by default."""
    cfg = settings or get_settings()
    explicit = cfg.definite_assurance_enforce_double_insurance
    if explicit is not None:
        return bool(explicit)
    base = (cfg.definite_assurance_base_url or "").lower()
    if "uat" in base or "localhost" in base:
        return False
    if cfg.app_env == "development":
        return False
    return True


def _as_bool(value: Any) -> bool | None:
    """Interpret a provider flag that may be a bool, number, or string."""
    if isinstance(value, bool):
        return value
    if value is None:
        return None
    if isinstance(value, (int, float)):
        return value != 0
    text = str(value).strip().lower()
    if text in _TRUE_WORDS:
        return True
    if text in _FALSE_WORDS:
        return False
    return None


def _candidate_scopes(payload: dict[str, Any]) -> list[dict[str, Any]]:
    """The payload plus any single-level envelope the insurer wraps it in."""
    scopes = [payload]
    for key in ("data", "Data", "result", "Result", "response", "payload"):
        nested = payload.get(key)
        if isinstance(nested, dict):
            scopes.append(nested)
        elif isinstance(nested, list) and nested and isinstance(nested[0], dict):
            scopes.extend(item for item in nested if isinstance(item, dict))
    return scopes


def evaluate_double_insurance(payload: Any) -> DoubleInsuranceVerdict:
    """Classify the insurer's answer as CLEAR, DETECTED, or UNKNOWN.

    UNKNOWN means "this response does not answer the question" — an empty body, a
    shape we do not recognise, or a non-object. Callers decide what that means;
    see ``is_double_insurance_clear``.
    """
    if not isinstance(payload, dict) or not payload:
        return "UNKNOWN"

    verdict: DoubleInsuranceVerdict = "UNKNOWN"
    for scope in _candidate_scopes(payload):
        for key in _FLAG_KEYS:
            if key in scope:
                flag = _as_bool(scope[key])
                if flag is True:
                    return "DETECTED"
                if flag is False:
                    verdict = "CLEAR"
        for key in _STATUS_KEYS:
            status = str(scope.get(key) or "").strip().upper()
            if status in _DETECTED_STATUSES:
                return "DETECTED"
            if status in _CLEAR_STATUSES:
                verdict = "CLEAR"
        message = str(scope.get("message") or scope.get("Message") or "").lower()
        if "active certificate" in message or ("double" in message and "detected" in message):
            return "DETECTED"
        if "no active" in message or "not found" in message:
            verdict = "CLEAR"
    return verdict


def is_double_insurance_clear(payload: Any, *, settings: Settings | None = None) -> bool:
    """True when the vehicle may be covered.

    An unreadable answer is not a clear answer: where the rule is enforced, silence
    from the insurer must not be recorded as "no other cover in force".
    """
    verdict = evaluate_double_insurance(payload)
    if verdict == "DETECTED":
        return False
    if verdict == "UNKNOWN":
        return not should_enforce_double_insurance(settings)
    return True
