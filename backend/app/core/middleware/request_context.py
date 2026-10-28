"""Request / job / correlation ID middleware."""

from collections.abc import Callable

import structlog
from starlette.middleware.base import BaseHTTPMiddleware
from starlette.requests import Request
from starlette.responses import Response

from app.core.logging.context import (
    clear_context,
    new_correlation_id,
    new_job_id,
    new_request_id,
    set_correlation_id,
    set_job_id,
    set_request_id,
)


class RequestContextMiddleware(BaseHTTPMiddleware):
    async def dispatch(self, request: Request, call_next: Callable) -> Response:
        clear_context()
        request_id = request.headers.get("X-Request-ID") or new_request_id()
        job_id = request.headers.get("X-Job-ID") or new_job_id()
        correlation_id = request.headers.get("X-Correlation-ID") or new_correlation_id()

        set_request_id(request_id)
        set_job_id(job_id)
        set_correlation_id(correlation_id)

        request.state.request_id = request_id
        request.state.job_id = job_id
        request.state.correlation_id = correlation_id

        structlog.contextvars.clear_contextvars()
        structlog.contextvars.bind_contextvars(
            request_id=request_id,
            job_id=job_id,
            correlation_id=correlation_id,
            path=request.url.path,
            method=request.method,
        )

        try:
            response = await call_next(request)
        finally:
            structlog.contextvars.clear_contextvars()

        response.headers["X-Request-ID"] = request_id
        response.headers["X-Job-ID"] = job_id
        response.headers["X-Correlation-ID"] = correlation_id
        return response
