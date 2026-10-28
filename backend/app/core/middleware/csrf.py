"""CSRF protection for cookie-authenticated mutating requests."""

from collections.abc import Callable
import hmac

from starlette.middleware.base import BaseHTTPMiddleware
from starlette.requests import Request
from starlette.responses import JSONResponse, Response

from app.core.config import get_settings
from app.core.logging.context import get_job_id, get_request_id
from app.core.responses import error_response

SAFE_METHODS = {"GET", "HEAD", "OPTIONS", "TRACE"}


def _is_guest_session_mint(request: Request) -> bool:
    """Welcome-screen capability mint/reuse — may bootstrap CSRF once."""
    path = request.url.path.rstrip("/")
    return request.method == "POST" and path.endswith("/insurance/guest/session")


def _is_password_login(request: Request) -> bool:
    """Email/password sign-in is a credential bootstrap, not a cookie mutation.

    A leftover guest or stale session cookie must not block users in the
    users table. Origin is still allowlisted when the browser sends it.
    """
    path = request.url.path.rstrip("/")
    return request.method == "POST" and path.endswith("/auth/login")


class CsrfMiddleware(BaseHTTPMiddleware):
    async def dispatch(self, request: Request, call_next: Callable) -> Response:
        settings = get_settings()
        if request.method in SAFE_METHODS:
            return await call_next(request)

        has_session_cookie = settings.access_cookie_name in request.cookies or (
            settings.refresh_cookie_name in request.cookies
        )
        has_guest_cookie = settings.guest_cookie_name in request.cookies

        # Bearer-only clients skip cookie CSRF. A Bearer header must not disable
        # CSRF when a session or guest cookie is also present — that cookie is
        # still usable by a cross-site form.
        auth = request.headers.get("Authorization", "")
        if (
            auth.lower().startswith("bearer ")
            and not has_session_cookie
            and not has_guest_cookie
        ):
            return await call_next(request)

        if not has_session_cookie and not has_guest_cookie:
            return await call_next(request)

        origin = (request.headers.get("origin") or "").strip()
        cookie_token = request.cookies.get(settings.csrf_cookie_name)
        header_token = request.headers.get(settings.csrf_header_name)

        # Stale guest cookie without a CSRF cookie (e.g. after logout cleared
        # ss_csrf only): allow mint/reuse when Origin is allowlisted so the
        # handler can re-issue the double-submit pair. All other guest
        # mutations still require a matching header once CSRF exists.
        csrf_ok = bool(
            cookie_token
            and header_token
            and hmac.compare_digest(cookie_token, header_token)
        )
        if not csrf_ok:
            bootstrap_guest_mint = (
                _is_guest_session_mint(request)
                and has_guest_cookie
                and not cookie_token
                and bool(origin)
                and origin in settings.cors_origin_list
            )
            if not bootstrap_guest_mint and not _is_password_login(request):
                return JSONResponse(
                    status_code=403,
                    content=error_response(
                        code="CSRF_VALIDATION_FAILED",
                        message="CSRF validation failed",
                        request_id=get_request_id(),
                        job_id=get_job_id(),
                    ),
                )

        # Origin allowlist check when Origin present
        if origin and origin not in settings.cors_origin_list:
            return JSONResponse(
                status_code=403,
                content=error_response(
                    code="ORIGIN_NOT_ALLOWED",
                    message="Request origin is not allowed",
                    request_id=get_request_id(),
                    job_id=get_job_id(),
                ),
            )

        # Guest mutations always require Origin (no cookie-less CSRF bypass)
        if has_guest_cookie and not has_session_cookie and not origin:
            return JSONResponse(
                status_code=403,
                content=error_response(
                    code="ORIGIN_REQUIRED",
                    message="Trusted origin is required for guest requests",
                    request_id=get_request_id(),
                    job_id=get_job_id(),
                ),
            )

        return await call_next(request)
