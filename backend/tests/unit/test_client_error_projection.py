"""Production responses never carry database internals; development is structured."""

from __future__ import annotations

from sqlalchemy.exc import IntegrityError, OperationalError

from app.core.config import Settings
from app.core.exceptions import ValidationAppError
from app.core.exceptions.sanitize import (
    client_debug_enabled,
    project_app_error,
    project_unexpected_error,
    public_error_details,
    public_error_message,
    redact_public_payload,
    structured_debug,
)
from app.core.responses import error_response, success_response


def _prod() -> Settings:
    return Settings(
        app_env="production",
        database_url="postgresql+asyncpg://u:p@db.internal:5432/starserve",
    )


def _dev() -> Settings:
    return Settings(
        app_env="development",
        database_url="postgresql+asyncpg://starserve:starserve@localhost:5432/starserve",
    )


def test_client_debug_is_development_only() -> None:
    assert client_debug_enabled(_dev()) is True
    assert client_debug_enabled(_prod()) is False
    assert client_debug_enabled(Settings(app_env="staging")) is False
    assert client_debug_enabled(Settings(app_env="backup")) is False


def test_production_message_drops_sql_and_dsn() -> None:
    sql = 'duplicate key value violates unique constraint "uq_customers_tenant_id_number"'
    assert (
        public_error_message(sql, fallback="An unexpected error occurred", settings=_prod())
        == "An unexpected error occurred"
    )
    dsn = "could not connect: postgresql+asyncpg://user:hunter2@db.internal:5432/starserve"
    assert (
        public_error_message(dsn, fallback="An unexpected error occurred", settings=_prod())
        == "An unexpected error occurred"
    )
    assert (
        public_error_message("Phone number is invalid", fallback="x", settings=_prod())
        == "Phone number is invalid"
    )


def test_production_details_drop_sql_keep_field_errors() -> None:
    cleaned = public_error_details(
        [
            {"field": "phone", "msg": "Use 9-15 digits, optional leading +"},
            {
                "sql": "INSERT INTO customers VALUES (...)",
                "constraint": "uq_customers_tenant_id_number",
                "dsn": "postgresql://u:p@db/starserve",
            },
            "DETAIL: Key (id_number)=(123) already exists.",
        ],
        settings=_prod(),
    )
    assert cleaned == [{"field": "phone", "msg": "Use 9-15 digits, optional leading +"}]


def test_existing_provider_blob_strip_still_holds() -> None:
    cleaned = public_error_details(
        [{"provider": {"secret": "x"}, "tried_periods": ["Monthly"], "raw": "{}"}]
    )
    assert cleaned == [{"tried_periods": ["Monthly"]}]


def test_integrity_error_is_conflict_without_schema_in_production() -> None:
    exc = IntegrityError(
        "INSERT INTO customers (id_number) VALUES (%(id_number)s)",
        {"id_number": "12345678"},
        Exception('duplicate key value violates unique constraint "uq_customers"'),
    )
    view = project_unexpected_error(exc, _prod())
    assert view.http_status == 409
    assert view.code == "CONFLICT"
    assert view.debug is None
    assert "customers" not in view.message
    assert "uq_customers" not in view.message
    assert "INSERT" not in view.message


def test_integrity_error_debug_in_development_is_structured() -> None:
    exc = IntegrityError(
        "INSERT INTO customers (id_number) VALUES (%(id_number)s)",
        {"id_number": "12345678"},
        Exception('duplicate key value violates unique constraint "uq_customers"'),
    )
    view = project_unexpected_error(exc, _dev())
    assert view.http_status == 409
    assert view.debug is not None
    assert view.debug["exception_type"] == "IntegrityError"
    assert view.debug["db"]["statement_verb"] == "INSERT"
    assert "12345678" not in str(view.debug)
    assert "postgresql://" not in str(view.debug)
    assert "params" not in view.debug


def test_operational_error_is_generic_unavailable() -> None:
    exc = OperationalError(
        "SELECT 1",
        {},
        Exception("password authentication failed for user \"starserve\""),
    )
    view = project_unexpected_error(exc, _prod())
    assert view.http_status == 503
    assert view.debug is None
    assert "password" not in view.message.lower()
    assert "starserve" not in view.message
    assert "SELECT" not in view.message


def test_app_error_with_sql_message_is_rewritten_in_production() -> None:
    exc = ValidationAppError(
        'INSERT INTO policies failed: relation "policies" does not exist'
    )
    view = project_app_error(exc, _prod())
    assert view.message == "The request contains invalid information"
    assert view.debug is None
    assert "policies" not in view.message


def test_app_error_sql_message_keeps_debug_in_development() -> None:
    exc = ValidationAppError(
        'INSERT INTO policies failed: relation "policies" does not exist'
    )
    view = project_app_error(exc, _dev())
    assert view.debug is not None
    assert view.debug["exception_type"] == "ValidationAppError"
    assert "postgresql://" not in view.debug["message"]


def test_success_envelope_strips_dsn_keys() -> None:
    body = success_response(
        {
            "id": "1",
            "database_url": "postgresql+asyncpg://u:secret@db/starserve",
            "note": "ok",
        }
    )
    assert "database_url" not in body["data"]
    assert body["data"]["note"] == "ok"


def test_error_envelope_omits_debug_when_absent() -> None:
    body = error_response(code="INTERNAL_ERROR", message="An unexpected error occurred")
    assert "debug" not in body


def test_error_envelope_includes_structured_debug() -> None:
    body = error_response(
        code="CONFLICT",
        message="The request conflicts with the current state",
        debug=structured_debug(
            IntegrityError("INSERT INTO x (id) VALUES (1)", {}, Exception("dup"))
        ),
    )
    assert body["debug"]["exception_type"] == "IntegrityError"
    assert body["debug"]["db"]["statement_verb"] == "INSERT"


def test_public_payload_redacts_embedded_dsn() -> None:
    cleaned = redact_public_payload(
        {"hint": "use postgresql+asyncpg://u:hunter2@db.internal:5432/starserve"},
        settings=_prod(),
    )
    assert "hunter2" not in str(cleaned)
    assert "postgresql+" not in str(cleaned)
