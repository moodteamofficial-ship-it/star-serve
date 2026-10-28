"""Public USSD provider callback — HTTPS endpoint for Birdview (*652#).

Birdview contract:
  GET /callback?SESSIONID=&MSISDN=&USSDCODE=&INPUT=
  HTTP 200 text/plain body starting with CON or END
  Always 200 (including application errors) — never 4xx/5xx to the aggregator
"""

from __future__ import annotations

from typing import Annotated, Any
from uuid import UUID, uuid4

from fastapi import APIRouter, Depends, Request, Response
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import get_settings
from app.core.database.rls import set_rls_context
from app.core.dependencies.auth import get_db
from app.core.logging import get_logger
from app.modules.insurance.guest_session import resolve_guest_tenant_id
from app.modules.ussd.engine import UssdEngine, resolve_provider
from app.modules.ussd.enums import UssdProviderKind
from app.modules.ussd.models import UssdProviderSetting
from app.modules.ussd.providers import get_adapter
from app.modules.ussd.providers.birdview import (
    BirdviewAdapter,
    looks_like_birdview,
    normalize_ussd_code,
)

logger = get_logger(__name__)

router = APIRouter(prefix="/ussd", tags=["USSD"])

_UNAVAILABLE = "Service temporarily unavailable. Please try again."


class _AuthView:
    def __init__(self, row: UssdProviderSetting | None, *, allow_unauthenticated: bool) -> None:
        self.auth_secret = (row.auth_secret_encrypted if row else None) or ""
        self.auth_header_name = (row.auth_header_name if row else None) or "X-USSD-Secret"
        self.allowed_ips = list(row.allowed_ips or []) if row else []
        self.allow_unauthenticated = allow_unauthenticated


def _safe_end(adapter: Any, message: str = _UNAVAILABLE) -> Response:
    render = getattr(adapter, "render", None)
    if callable(render):
        return render(text=message, response_type="END")
    return BirdviewAdapter().render(text=message, response_type="END")


@router.api_route("/callback", methods=["GET", "POST"])
async def ussd_callback(
    request: Request,
    db: Annotated[AsyncSession, Depends(get_db)],
) -> Response:
    """Birdview (and compatible) callback. Share: ``/api/v1/ussd/callback``."""
    settings = get_settings()
    # Default to Birdview renderer so any early failure still satisfies the contract.
    adapter: Any = BirdviewAdapter()

    if not getattr(settings, "ussd_enabled", True):
        return _safe_end(adapter)

    body_bytes = b""
    try:
        if request.method.upper() == "POST":
            body_bytes = await request.body()

            async def _receive() -> dict:
                return {"type": "http.request", "body": body_bytes, "more_body": False}

            request = Request(request.scope, _receive)

        # Resolve service / tenant. USSDCODE is for provider lookup only — not menu routing.
        service_code = ""
        if looks_like_birdview(request, body_bytes or None):
            from app.modules.ussd.providers.birdview import extract_birdview_params

            params = extract_birdview_params(request, body_bytes or None)
            service_code = normalize_ussd_code(params.get("USSDCODE"))
        elif body_bytes:
            content_type = (request.headers.get("content-type") or "").lower()
            if "application/json" in content_type:
                import json

                data = json.loads(body_bytes.decode() or "{}")
            else:
                from urllib.parse import parse_qs

                parsed = parse_qs(body_bytes.decode(), keep_blank_values=True)
                data = {k: (v[0] if v else "") for k, v in parsed.items()}
            service_code = str(
                data.get("serviceCode") or data.get("service_code") or data.get("USSDCODE") or ""
            ).strip()
            service_code = normalize_ussd_code(service_code)

        provider_row = None
        if service_code:
            provider_row = await resolve_provider(db, service_code=service_code)
        if provider_row is None:
            # Prefer configured Birdview row, else any enabled provider.
            provider_row = await db.scalar(
                select(UssdProviderSetting)
                .where(
                    UssdProviderSetting.enabled.is_(True),
                    UssdProviderSetting.provider_kind == UssdProviderKind.BIRDVIEW.value,
                )
                .limit(1)
            )
        if provider_row is None:
            provider_row = await db.scalar(
                select(UssdProviderSetting).where(UssdProviderSetting.enabled.is_(True)).limit(1)
            )

        birdview_request = looks_like_birdview(request, body_bytes or None)
        kind = (
            UssdProviderKind.BIRDVIEW.value
            if birdview_request
            else (
                provider_row.provider_kind
                if provider_row
                else UssdProviderKind.BIRDVIEW.value
            )
        )
        adapter = get_adapter(kind)

        allow_unauth = (not settings.is_production) or bool(
            getattr(settings, "ussd_allow_unauthenticated", False)
        )
        # Birdview go-live: HTTPS URL with optional secret. If no secret is set, allow.
        if kind == UssdProviderKind.BIRDVIEW.value:
            allow_unauth = allow_unauth or not bool(
                (provider_row.auth_secret_encrypted if provider_row else None) or ""
            )

        try:
            await adapter.authenticate(
                request, _AuthView(provider_row, allow_unauthenticated=allow_unauth)
            )
        except Exception:
            logger.warning("ussd_callback_auth_failed", exc_info=True)
            return _safe_end(adapter)

        if kind == UssdProviderKind.BIRDVIEW.value and hasattr(adapter, "parse"):
            # Pass cached body for POST-compatible test harnesses.
            try:
                callback = await adapter.parse(request, body_bytes or None)  # type: ignore[call-arg]
            except TypeError:
                callback = await adapter.parse(request)
        else:
            callback = await adapter.parse(request)

        if provider_row is not None:
            tenant_id = UUID(str(provider_row.tenant_id))
        else:
            tenant_id = await resolve_guest_tenant_id(db)

        await set_rls_context(db, tenant_id=tenant_id, is_platform_admin=False)
        correlation_id = getattr(request.state, "request_id", None) or str(uuid4())

        engine = UssdEngine()
        result = await engine.handle(
            db,
            tenant_id=tenant_id,
            provider_kind=callback.provider_kind,
            provider_session_id=callback.session_id,
            service_code=callback.service_code or service_code,
            msisdn=callback.msisdn,
            text=callback.text,
            correlation_id=correlation_id,
            is_test=False,
            idempotency_key=callback.idempotency_key,
        )
        await db.commit()
        return adapter.render(text=result.text, response_type=result.response_type)
    except Exception:
        try:
            await db.rollback()
        except Exception:
            logger.warning("ussd_callback_rollback_failed", exc_info=True)
        logger.exception("ussd_callback_failed")
        return _safe_end(adapter)


@router.get("/health")
async def ussd_health() -> dict:
    settings = get_settings()
    return {
        "success": True,
        "data": {
            "enabled": bool(getattr(settings, "ussd_enabled", True)),
            "callback_path": "/api/v1/ussd/callback",
            "callback_url": (
                "https://quote.starserveinsuranceagency.com/api/v1/ussd/callback"
                if "quote.starserveinsuranceagency.com"
                in (getattr(settings, "email_app_url", "") or "")
                else "/api/v1/ussd/callback"
            ),
            "callback_methods": ["GET", "POST"],
            "provider": "birdview",
            "contract": {
                "request": "GET ?SESSIONID=&MSISDN=&USSDCODE=&INPUT=",
                "response": "text/plain CON|END",
                "input": "latest_only",
                "max_chars": 160,
                "session_idle_seconds": 180,
            },
            "service_code": getattr(settings, "ussd_default_service_code", "*652*6#"),
        },
    }
