"""Client error projection — production never sees database internals.

Development may attach a structured ``debug`` object. Secrets (DSNs,
passwords, tokens) are redacted in every environment. ``APP_DEBUG`` is
ignored: only ``APP_ENV=development`` enables client debug.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from typing import Any

from app.core.config import Settings, get_settings

# Credentials / connection material — never on a client body.
_CREDENTIAL_KEYS = frozenset(
    {
        "dsn",
        "database_url",
        "dedicated_database_dsn",
        "password",
        "password_hash",
        "passwd",
        "token",
        "refresh_token",
        "access_token",
        "authorization",
        "cookie",
        "secret",
        "api_key",
        "apikey",
        "partner_id",
        "partnerid",
        "private_key",
    }
)

# Driver / SQL blobs — stripped from error details (not from ordinary success fields).
_ERROR_BLOB_KEYS = frozenset(
    {
        "provider",
        "raw",
        "orig",
        "params",
        "statement",
        "sql",
    }
)

_SECRET_KEYS = _CREDENTIAL_KEYS | _ERROR_BLOB_KEYS

# Postgres / SQLAlchemy diagnostic keys — allowed in dev debug only.
_DB_DIAGNOSTIC_KEYS = frozenset(
    {
        "constraint",
        "constraint_name",
        "table",
        "table_name",
        "column",
        "column_name",
        "schema",
        "pgcode",
        "sqlstate",
        "hint",
        "context",
        "connection",
        "driver_error",
    }
)

_SECRET_KEY_SUFFIXES = ("_dsn", "_password", "_secret", "_token", "_private_key")

_DSN_RE = re.compile(
    r"(?i)\b(?:postgresql(?:\+asyncpg)?|postgres|mysql|mongodb|redis|amqp)://\S+"
)
_CRED_RE = re.compile(
    r"(?i)\b(password|passwd|pwd|secret|api[_-]?key|access[_-]?token|refresh[_-]?token)"
    r"\s*[:=]\s*\S+"
)
_SQL_DIAG_RE = re.compile(
    r"(?is)("
    r"\b(SELECT|INSERT|UPDATE|DELETE|ALTER|CREATE|DROP|TRUNCATE|GRANT|REVOKE)\b"
    r".{0,400}\b(FROM|INTO|TABLE|SET|VALUES)\b"
    r"|duplicate key value violates unique constraint"
    r"|violates (?:foreign key|not-null|check) constraint"
    r"|(?:relation|column|constraint|index|sequence)\s+\"[^\"]+\""
    r"|\b(?:DETAIL|HINT|CONTEXT|SQLSTATE)\s*:"
    r"|server closed the connection unexpectedly"
    r"|remaining connection slots are reserved"
    r"|could not connect to server"
    r"|password authentication failed"
    r"|SSL connection has been closed unexpectedly"
    r")"
)

_STATEMENT_VERB_RE = re.compile(
    r"\b(SELECT|INSERT|UPDATE|DELETE|ALTER|CREATE|DROP|TRUNCATE|BEGIN|COMMIT|ROLLBACK)\b",
    re.IGNORECASE,
)


def client_debug_enabled(settings: Settings | None = None) -> bool:
    """Structured client debug is development-only. Production/staging/backup never get it."""
    env = (settings or get_settings()).app_env
    return env == "development"


def production_response_strict(settings: Settings | None = None) -> bool:
    """True when HTTP bodies must not carry database diagnostics."""
    return not client_debug_enabled(settings)


def _key_is_secret(key: str) -> bool:
    lowered = key.lower()
    return lowered in _SECRET_KEYS or lowered.endswith(_SECRET_KEY_SUFFIXES)


def _key_is_db_diagnostic(key: str) -> bool:
    return key.lower() in _DB_DIAGNOSTIC_KEYS


def contains_secret(text: str) -> bool:
    return bool(_DSN_RE.search(text) or _CRED_RE.search(text))


def contains_db_diagnostics(text: str) -> bool:
    return bool(_SQL_DIAG_RE.search(text))


def redact_sensitive_text(text: str) -> str:
    """Always strip credentials / DSNs. Safe in every environment."""
    cleaned = _DSN_RE.sub("[redacted-dsn]", text)
    cleaned = _CRED_RE.sub(lambda m: f"{m.group(1)}=[redacted]", cleaned)
    return cleaned


def public_error_message(
    message: str | None,
    *,
    fallback: str,
    settings: Settings | None = None,
) -> str:
    text = (message or "").strip() or fallback
    if contains_secret(text):
        return fallback
    if production_response_strict(settings) and contains_db_diagnostics(text):
        return fallback
    return text


def public_error_details(
    details: list[Any] | None,
    *,
    settings: Settings | None = None,
) -> list[Any]:
    """Return a client-safe copy of exception details."""
    if not details:
        return []
    strict = production_response_strict(settings)
    out: list[Any] = []
    for item in details:
        cleaned = _sanitize_value(item, strict=strict, allow_db_keys=False)
        if cleaned in (None, {}, []):
            continue
        out.append(cleaned)
    return out


def _sanitize_value(value: Any, *, strict: bool, allow_db_keys: bool) -> Any:
    if isinstance(value, dict):
        cleaned: dict[str, Any] = {}
        for key, item in value.items():
            name = str(key)
            if _key_is_secret(name):
                continue
            if strict and _key_is_db_diagnostic(name) and not allow_db_keys:
                continue
            nested = _sanitize_value(item, strict=strict, allow_db_keys=allow_db_keys)
            if nested in (None, {}, []):
                continue
            cleaned[name] = nested
        return cleaned
    if isinstance(value, list):
        return [
            item
            for item in (
                _sanitize_value(entry, strict=strict, allow_db_keys=allow_db_keys)
                for entry in value
            )
            if item not in (None, {}, [])
        ]
    if isinstance(value, str):
        text = redact_sensitive_text(value)
        if contains_secret(text):
            return None
        if strict and contains_db_diagnostics(text):
            return None
        return text
    if isinstance(value, (int, float, bool)):
        return value
    return None


def redact_public_payload(value: Any, *, settings: Settings | None = None) -> Any:
    """Walk a success/error payload and drop secret keys / DSN strings.

    Used as the last line of defense so a future handler cannot leak a DSN
    just because it put the field on a public model.
    """
    strict = production_response_strict(settings)
    if isinstance(value, dict):
        return {
            key: redact_public_payload(item, settings=settings)
            for key, item in value.items()
            if str(key).lower() not in _CREDENTIAL_KEYS
            and not str(key).lower().endswith(_SECRET_KEY_SUFFIXES)
        }
    if isinstance(value, list):
        return [redact_public_payload(item, settings=settings) for item in value]
    if isinstance(value, str):
        text = redact_sensitive_text(value)
        if contains_secret(text):
            return "[redacted]"
        if strict and contains_db_diagnostics(text):
            return "[redacted]"
        return text
    return value


def _sqlstate(exc: BaseException) -> str | None:
    orig = getattr(exc, "orig", None)
    for candidate in (orig, exc):
        if candidate is None:
            continue
        for attr in ("sqlstate", "pgcode"):
            value = getattr(candidate, attr, None)
            if value:
                return str(value)
        diag = getattr(candidate, "diag", None)
        if diag is not None:
            value = getattr(diag, "sqlstate", None)
            if value:
                return str(value)
    return None


def _diag_field(exc: BaseException, *names: str) -> str | None:
    orig = getattr(exc, "orig", None)
    for candidate in (orig, exc):
        if candidate is None:
            continue
        for name in names:
            value = getattr(candidate, name, None)
            if value:
                return str(value)
        diag = getattr(candidate, "diag", None)
        if diag is None:
            continue
        for name in names:
            value = getattr(diag, name, None)
            if value:
                return str(value)
    return None


def _statement_verb(exc: BaseException) -> str | None:
    statement = getattr(exc, "statement", None)
    if not statement:
        return None
    match = _STATEMENT_VERB_RE.search(str(statement))
    return match.group(1).upper() if match else None


def structured_debug(exc: BaseException) -> dict[str, Any]:
    """Development-only. Secrets redacted. No bind params, no DSN, no stack."""
    message = redact_sensitive_text(str(getattr(exc, "orig", None) or exc))
    if contains_secret(message):
        message = "[redacted]"
    debug: dict[str, Any] = {
        "exception_type": type(exc).__name__,
        "origin": type(exc).__module__,
        "message": message[:500],
    }
    sqlstate = _sqlstate(exc)
    verb = _statement_verb(exc)
    constraint = _diag_field(exc, "constraint_name", "constraint")
    table = _diag_field(exc, "table_name", "table")
    db: dict[str, Any] = {}
    if sqlstate:
        db["sqlstate"] = sqlstate
    if verb:
        db["statement_verb"] = verb
    if constraint:
        db["constraint"] = constraint
    if table:
        db["table"] = table
    if db:
        debug["db"] = db
    return debug


@dataclass(slots=True)
class ClientErrorView:
    code: str
    http_status: int
    message: str
    details: list[Any] = field(default_factory=list)
    debug: dict[str, Any] | None = None


def project_app_error(exc: Any, settings: Settings | None = None) -> ClientErrorView:
    """StarServeError → public envelope."""
    fallback = getattr(type(exc), "message", None) or "An unexpected error occurred"
    details = public_error_details(getattr(exc, "details", None), settings=settings)
    view = ClientErrorView(
        code=getattr(exc, "code", "INTERNAL_ERROR"),
        http_status=int(getattr(exc, "http_status", 500)),
        message=public_error_message(
            getattr(exc, "message", None), fallback=fallback, settings=settings
        ),
        details=details,
    )
    raw = str(getattr(exc, "message", "") or "")
    if client_debug_enabled(settings) and (
        contains_secret(raw) or contains_db_diagnostics(raw)
    ):
        view.debug = {
            "exception_type": type(exc).__name__,
            "origin": type(exc).__module__,
            "message": redact_sensitive_text(raw)[:500],
        }
    return view


def project_unexpected_error(exc: BaseException, settings: Settings | None = None) -> ClientErrorView:
    """SQLAlchemy / unknown errors. Production is generic; development is structured."""
    from sqlalchemy.exc import IntegrityError, OperationalError, SQLAlchemyError

    from app.core.exceptions.base import ConflictError

    if isinstance(exc, IntegrityError):
        code, status, message = ConflictError.code, ConflictError.http_status, ConflictError.message
    elif isinstance(exc, OperationalError):
        code, status, message = (
            "INTERNAL_ERROR",
            503,
            "The service is temporarily unavailable",
        )
    elif isinstance(exc, SQLAlchemyError):
        code, status, message = "INTERNAL_ERROR", 500, "An unexpected error occurred"
    else:
        code, status, message = "INTERNAL_ERROR", 500, "An unexpected error occurred"

    debug = structured_debug(exc) if client_debug_enabled(settings) else None
    return ClientErrorView(code=code, http_status=status, message=message, debug=debug)
