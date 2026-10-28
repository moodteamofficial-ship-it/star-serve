"""Correlation identifiers for request/job tracing."""

from contextvars import ContextVar
from typing import Any
from uuid import uuid4

import ulid

_request_id: ContextVar[str | None] = ContextVar("request_id", default=None)
_job_id: ContextVar[str | None] = ContextVar("job_id", default=None)
_correlation_id: ContextVar[str | None] = ContextVar("correlation_id", default=None)
_tenant_id: ContextVar[str | None] = ContextVar("tenant_id", default=None)
_user_id: ContextVar[str | None] = ContextVar("user_id", default=None)


def new_request_id() -> str:
    return f"REQ-{ulid.new()}"


def new_job_id() -> str:
    return f"JOB-{ulid.new()}"


def new_correlation_id() -> str:
    return f"CORR-{ulid.new()}"


def new_uuid() -> str:
    return str(uuid4())


def set_request_id(value: str) -> None:
    _request_id.set(value)


def get_request_id() -> str | None:
    return _request_id.get()


def set_job_id(value: str) -> None:
    _job_id.set(value)


def get_job_id() -> str | None:
    return _job_id.get()


def set_correlation_id(value: str) -> None:
    _correlation_id.set(value)


def get_correlation_id() -> str | None:
    return _correlation_id.get()


def set_tenant_id(value: str | None) -> None:
    _tenant_id.set(value)


def get_tenant_id() -> str | None:
    return _tenant_id.get()


def set_user_id(value: str | None) -> None:
    _user_id.set(value)


def get_user_id() -> str | None:
    return _user_id.get()


def clear_context() -> None:
    _request_id.set(None)
    _job_id.set(None)
    _correlation_id.set(None)
    _tenant_id.set(None)
    _user_id.set(None)


def binding_dict() -> dict[str, Any]:
    return {
        "request_id": get_request_id(),
        "job_id": get_job_id(),
        "correlation_id": get_correlation_id(),
        "tenant_id": get_tenant_id(),
        "user_id": get_user_id(),
    }
