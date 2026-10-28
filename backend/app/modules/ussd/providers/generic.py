"""Generic form-urlencoded USSD callback (Africa's Talking shaped).

Production protocol details remain pending real provider onboarding.
Supported request fields (form or JSON):
  sessionId, phoneNumber, text, serviceCode
Optional: networkCode

Continue response: plain text prefixed with CON
End response: plain text prefixed with END
"""

from __future__ import annotations

import hmac
from typing import Any

from fastapi import Response
from starlette.requests import Request

from app.core.exceptions import AuthenticationError, ValidationAppError
from app.modules.ussd.enums import UssdProviderKind, UssdResponseType
from app.modules.ussd.providers.base import ProviderCallback


class GenericFormAdapter:
    kind = UssdProviderKind.GENERIC_FORM.value

    async def authenticate(self, request: Request, settings: Any) -> None:
        expected = (getattr(settings, "auth_secret", None) or "").strip()
        header_name = (getattr(settings, "auth_header_name", None) or "X-USSD-Secret").strip()
        if not expected:
            # Simulator / unset secret: allow only non-production via settings flag.
            if getattr(settings, "allow_unauthenticated", False):
                return
            raise AuthenticationError("USSD provider secret is not configured")
        provided = (request.headers.get(header_name) or "").strip()
        if not provided or not hmac.compare_digest(provided, expected):
            raise AuthenticationError("Invalid USSD provider credentials")
        from app.core.security.request import client_ip, ip_in_allowlist

        allowed = [str(x).strip() for x in (getattr(settings, "allowed_ips", None) or []) if str(x).strip()]
        if allowed:
            ip = client_ip(request)
            if not ip or not ip_in_allowlist(ip, ",".join(allowed)):
                raise AuthenticationError("USSD callback IP is not allowed")

    async def parse(self, request: Request) -> ProviderCallback:
        content_type = (request.headers.get("content-type") or "").lower()
        if "application/json" in content_type:
            body = await request.json()
            data = body if isinstance(body, dict) else {}
        else:
            form = await request.form()
            data = {k: str(v) for k, v in form.items()}
        session_id = str(data.get("sessionId") or data.get("session_id") or "").strip()
        msisdn = str(data.get("phoneNumber") or data.get("msisdn") or "").strip()
        service_code = str(data.get("serviceCode") or data.get("service_code") or "").strip()
        text = data.get("text")
        if text is not None:
            text = str(text)
            # Africa's Talking sends the full path joined by *; use the last segment.
            if "*" in text:
                text = text.split("*")[-1]
        if not session_id or not msisdn:
            raise ValidationAppError("USSD callback is missing sessionId or phoneNumber")
        idem = (
            request.headers.get("X-Idempotency-Key")
            or f"{session_id}:{text or ''}:{data.get('networkCode') or ''}"
        )
        return ProviderCallback(
            provider_kind=self.kind,
            service_code=service_code,
            session_id=session_id,
            msisdn=msisdn,
            text=text,
            network_code=str(data.get("networkCode") or "") or None,
            raw=dict(data),
            idempotency_key=str(idem)[:128],
        )

    def render(self, *, text: str, response_type: str) -> Response:
        prefix = "END" if response_type == UssdResponseType.END.value else "CON"
        body = f"{prefix} {(text or '').strip() or 'Service temporarily unavailable. Please try again.'}"
        return Response(
            content=body,
            status_code=200,
            media_type="text/plain; charset=utf-8",
            headers={"Cache-Control": "no-store"},
        )


class AfricasTalkingAdapter(GenericFormAdapter):
    kind = UssdProviderKind.AFRICAS_TALKING.value
