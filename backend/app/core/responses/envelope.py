"""Standard API response envelopes."""

from typing import Any, Generic, TypeVar

from pydantic import BaseModel, Field

from app.core.exceptions.sanitize import redact_public_payload

T = TypeVar("T")


class ErrorBody(BaseModel):
    code: str
    message: str
    details: list[Any] = Field(default_factory=list)


class ApiResponse(BaseModel, Generic[T]):
    success: bool = True
    data: T | None = None
    message: str = "Operation completed successfully"
    requestId: str | None = None
    jobId: str | None = None


class ApiErrorResponse(BaseModel):
    success: bool = False
    error: ErrorBody
    requestId: str | None = None
    jobId: str | None = None
    debug: dict[str, Any] | None = None


def success_response(
    data: Any = None,
    *,
    message: str = "Operation completed successfully",
    request_id: str | None = None,
    job_id: str | None = None,
) -> dict[str, Any]:
    from app.core.jsoning import json_ready

    return {
        "success": True,
        "data": json_ready(redact_public_payload(data)),
        "message": message,
        "requestId": request_id,
        "jobId": job_id,
    }


def error_response(
    *,
    code: str,
    message: str,
    details: list[Any] | None = None,
    request_id: str | None = None,
    job_id: str | None = None,
    debug: dict[str, Any] | None = None,
) -> dict[str, Any]:
    body: dict[str, Any] = {
        "success": False,
        "error": {
            "code": code,
            "message": message,
            "details": redact_public_payload(details or []),
        },
        "requestId": request_id,
        "jobId": job_id,
    }
    if debug:
        body["debug"] = redact_public_payload(debug)
    return body
