"""Dashboard simulator adapter — same engine, JSON request/response, test flag."""

from __future__ import annotations

from typing import Any
from uuid import uuid4

from fastapi.responses import JSONResponse
from starlette.requests import Request

from app.core.config.settings import get_settings
from app.core.exceptions import ValidationAppError
from app.modules.ussd.enums import UssdProviderKind
from app.modules.ussd.providers.base import ProviderCallback


class SimulatorAdapter:
    kind = UssdProviderKind.SIMULATOR.value

    async def authenticate(self, request: Request, settings: Any) -> None:
        # Staff auth is enforced on the admin simulator route; no provider secret.
        return None

    async def parse(self, request: Request) -> ProviderCallback:
        body = await request.json()
        if not isinstance(body, dict):
            raise ValidationAppError("Simulator body must be a JSON object")
        session_id = str(body.get("session_id") or body.get("sessionId") or "").strip()
        if not session_id:
            session_id = f"sim-{uuid4().hex[:16]}"
        msisdn = str(body.get("msisdn") or body.get("phoneNumber") or "").strip()
        if not msisdn:
            raise ValidationAppError("Simulator requires msisdn")
        text = body.get("text")
        if text is not None:
            text = str(text)
        service_code = str(
            body.get("service_code")
            or body.get("serviceCode")
            or get_settings().ussd_default_service_code
        )
        return ProviderCallback(
            provider_kind=self.kind,
            service_code=service_code,
            session_id=session_id,
            msisdn=msisdn,
            text=text,
            raw=body,
            idempotency_key=str(body.get("idempotency_key") or "")[:128] or None,
        )

    def render(self, *, text: str, response_type: str) -> JSONResponse:
        return JSONResponse(
            {
                "success": True,
                "data": {
                    "text": text,
                    "response_type": response_type,
                    "test_mode": True,
                },
            }
        )
