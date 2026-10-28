"""Build a GuestContext for USSD so we reuse GuestService / GuestClaimService."""

from __future__ import annotations

from typing import Any
from uuid import UUID, uuid4

from starlette.requests import Request

from app.core.config import get_settings
from app.core.security.guest_capabilities import GUEST_CAPABILITIES, GuestContext
from app.modules.ussd.privacy import normalize_msisdn


def ussd_guest_context(*, tenant_id: UUID, guest_session_id: UUID | None = None) -> GuestContext:
    settings = get_settings()
    sid = guest_session_id or uuid4()
    ctx = GuestContext(
        session_id=sid,
        tenant_id=tenant_id,
        tenant_status="ACTIVE",
        app_env=settings.app_env,
        capabilities=GUEST_CAPABILITIES,
        jti=f"ussd:{sid}",
    )
    ctx.bind()
    return ctx


def prepare_ussd_request(
    *,
    msisdn: str,
    correlation_id: str,
    guest: GuestContext,
    is_test: bool = False,
) -> Request:
    """Request stand-in with guest session state so bind_guest_* helpers work."""
    request = Request(
        {
            "type": "http",
            "asgi": {"version": "3.0"},
            "http_version": "1.1",
            "method": "POST",
            "scheme": "https",
            "path": "/api/v1/ussd/callback",
            "raw_path": b"/api/v1/ussd/callback",
            "query_string": b"",
            "headers": [],
            "client": ("127.0.0.1", 0),
            "server": ("ussd.local", 443),
        }
    )
    jti = guest.jti or f"ussd:{guest.session_id}"
    request.state.request_id = correlation_id
    request.state.ussd_msisdn = normalize_msisdn(msisdn)
    request.state.ussd_is_test = is_test
    request.state.guest_jti = jti
    request.state.guest_context = guest
    request.state.guest_session = {
        "tenant_id": str(guest.tenant_id),
        "customers": [],
        "policies": [],
        "claims": [],
        "channel": "USSD",
    }
    return request
