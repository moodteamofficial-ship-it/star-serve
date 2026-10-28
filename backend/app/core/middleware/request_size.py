"""Reject oversized request bodies before they are fully buffered."""

from starlette.datastructures import Headers
from starlette.responses import JSONResponse
from starlette.types import ASGIApp, Receive, Scope, Send

from app.core.config import get_settings
from app.core.logging.context import get_job_id, get_request_id
from app.core.responses import error_response


def _too_large() -> JSONResponse:
    return JSONResponse(
        status_code=413,
        content=error_response(
            code="PAYLOAD_TOO_LARGE",
            message="Request body is too large",
            request_id=get_request_id(),
            job_id=get_job_id(),
        ),
    )


class RequestSizeLimitMiddleware:
    """ASGI middleware — Content-Length plus a hard cap on actual bytes.

    Implemented as raw ASGI (not BaseHTTPMiddleware) so the replayed body is
    what downstream FastAPI actually reads. Chunked uploads cannot skip the cap
    by omitting Content-Length.
    """

    def __init__(self, app: ASGIApp) -> None:
        self.app = app

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        if scope["type"] != "http":
            await self.app(scope, receive, send)
            return

        settings = get_settings()
        path = scope.get("path") or ""
        method = scope.get("method") or ""
        if "/claims/" in path and path.rstrip("/").endswith("/documents") and method == "POST":
            limit = int(getattr(settings, "claims_document_max_bytes", 0) or settings.max_request_body_bytes or 0)
        elif path.rstrip("/").endswith("/auth/me/avatar") and method == "POST":
            limit = int(getattr(settings, "avatar_max_bytes", 0) or settings.max_request_body_bytes or 0)
        else:
            limit = int(settings.max_request_body_bytes or 0)
        if limit <= 0:
            await self.app(scope, receive, send)
            return

        headers = Headers(scope=scope)
        raw = headers.get("content-length")
        if raw is not None:
            try:
                declared = int(raw)
            except ValueError:
                await _too_large()(scope, receive, send)
                return
            if declared < 0 or declared > limit:
                await _too_large()(scope, receive, send)
                return

        body = bytearray()
        while True:
            message = await receive()
            if message["type"] == "http.disconnect":
                return
            if message["type"] != "http.request":
                await self.app(scope, _replay(bytes(body), receive, first=message), send)
                return
            chunk = message.get("body", b"") or b""
            body.extend(chunk)
            if len(body) > limit:
                await _too_large()(scope, receive, send)
                return
            if not message.get("more_body", False):
                break

        await self.app(scope, _replay(bytes(body), receive), send)


def _replay(body: bytes, receive: Receive, first: dict | None = None) -> Receive:
    sent = False

    async def receive_replay() -> dict:
        nonlocal sent
        if first is not None and not sent:
            sent = True
            return first
        if not sent:
            sent = True
            return {"type": "http.request", "body": body, "more_body": False}
        return await receive()

    return receive_replay
