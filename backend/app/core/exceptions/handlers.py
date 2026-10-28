"""Central exception handlers — production never leaks database internals."""

from fastapi import FastAPI, Request
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse
from sqlalchemy.exc import SQLAlchemyError
from starlette.exceptions import HTTPException as StarletteHTTPException

from app.core.exceptions import StarServeError
from app.core.exceptions.sanitize import (
    client_debug_enabled,
    project_app_error,
    project_unexpected_error,
    public_error_details,
    public_error_message,
    structured_debug,
)
from app.core.logging import get_logger
from app.core.logging.context import get_job_id, get_request_id
from app.core.responses import error_response

logger = get_logger(__name__)

_FIELD_LABELS = {
    "full_name": "full name",
    "role_id": "role",
    "branch_id": "branch",
    "password": "password",
    "email": "email",
    "phone": "phone",
}


def _human_validation_message(errors: list[dict]) -> str | None:
    """Prefer the first field-level message over the generic 422 envelope copy."""
    for err in errors:
        raw = str(err.get("msg") or "").strip()
        if not raw:
            continue
        if raw.startswith("Value error, "):
            return raw[len("Value error, ") :].strip() or None
        loc = err.get("loc") or ()
        field = next(
            (str(part) for part in reversed(tuple(loc)) if part not in {"body", "query", "path"}),
            None,
        )
        label = _FIELD_LABELS.get(field or "", (field or "field").replace("_", " "))
        err_type = str(err.get("type") or "")
        if err_type in {"missing", "value_error.missing"}:
            return f"Enter a valid {label}"
        if "uuid" in err_type:
            return f"Select a valid {label}"
        if err_type.startswith("string_too_short"):
            return f"{label[:1].upper() + label[1:]} is too short"
        if err_type.startswith("string_too_long"):
            return f"{label[:1].upper() + label[1:]} is too long"
        if raw.startswith("Input should be"):
            return f"Enter a valid {label}"
    return None


def _ids(request: Request) -> tuple[str | None, str | None]:
    return (
        getattr(request.state, "request_id", get_request_id()),
        getattr(request.state, "job_id", get_job_id()),
    )


def _json(status: int, content: dict, headers: dict[str, str] | None = None) -> JSONResponse:
    return JSONResponse(status_code=status, content=content, headers=headers or None)


def register_exception_handlers(app: FastAPI) -> None:
    @app.exception_handler(StarServeError)
    async def starserve_error_handler(request: Request, exc: StarServeError) -> JSONResponse:
        headers: dict[str, str] = {}
        view = project_app_error(exc)
        if exc.http_status == 429 and view.details:
            first = view.details[0] if isinstance(view.details[0], dict) else None
            if first and "retry_after_seconds" in first:
                headers["Retry-After"] = str(int(first["retry_after_seconds"]))
        request_id, job_id = _ids(request)
        return _json(
            view.http_status,
            error_response(
                code=view.code,
                message=view.message,
                details=view.details,
                request_id=request_id,
                job_id=job_id,
                debug=view.debug,
            ),
            headers,
        )

    @app.exception_handler(RequestValidationError)
    async def validation_handler(request: Request, exc: RequestValidationError) -> JSONResponse:
        errors = list(exc.errors())
        details = public_error_details(
            [
                {
                    "loc": err.get("loc"),
                    "msg": err.get("msg"),
                    "type": err.get("type"),
                }
                for err in errors
            ]
        )
        message = _human_validation_message(errors) or "The request contains invalid information"
        request_id, job_id = _ids(request)
        return _json(
            422,
            error_response(
                code="VALIDATION_ERROR",
                message=message,
                details=details,
                request_id=request_id,
                job_id=job_id,
            ),
        )

    @app.exception_handler(StarletteHTTPException)
    async def http_handler(request: Request, exc: StarletteHTTPException) -> JSONResponse:
        request_id, job_id = _ids(request)
        message = public_error_message(
            str(exc.detail) if exc.detail else None,
            fallback="Request failed",
        )
        debug = structured_debug(exc) if client_debug_enabled() and message == "Request failed" else None
        return _json(
            exc.status_code,
            error_response(
                code="HTTP_ERROR",
                message=message,
                request_id=request_id,
                job_id=job_id,
                debug=debug,
            ),
        )

    @app.exception_handler(SQLAlchemyError)
    async def sqlalchemy_handler(request: Request, exc: SQLAlchemyError) -> JSONResponse:
        logger.exception("database_error", error_type=type(exc).__name__)
        view = project_unexpected_error(exc)
        request_id, job_id = _ids(request)
        return _json(
            view.http_status,
            error_response(
                code=view.code,
                message=view.message,
                request_id=request_id,
                job_id=job_id,
                debug=view.debug,
            ),
        )

    @app.exception_handler(Exception)
    async def unhandled_handler(request: Request, exc: Exception) -> JSONResponse:
        logger.exception("unhandled_exception", error_type=type(exc).__name__)
        view = project_unexpected_error(exc)
        request_id, job_id = _ids(request)
        return _json(
            view.http_status,
            error_response(
                code=view.code,
                message=view.message,
                request_id=request_id,
                job_id=job_id,
                debug=view.debug,
            ),
        )
