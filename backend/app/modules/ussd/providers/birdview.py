"""Birdview USSD partner contract (*652# extensions).

Inbound (GET):
  SESSIONID, MSISDN (+prefixed), USSDCODE (informational), INPUT (latest only)

Outbound (HTTP 200, text/plain):
  CON <screen>  — continue session
  END <screen>  — close session

Empty INPUT on a new SESSIONID means render the welcome screen. USSDCODE must
not drive menu routing. Despite the written contract, live Birdview may still
send cumulative INPUT joined by ``*`` (e.g. ``1*0``); we always use the last
segment so behaviour matches the latest keypress.
"""

from __future__ import annotations

import hmac
from typing import Any
from urllib.parse import parse_qs

from fastapi import Response
from starlette.requests import Request

from app.modules.ussd.enums import UssdProviderKind, UssdResponseType
from app.modules.ussd.providers.base import ProviderCallback

# Birdview guidance: keep each screen under ~160 characters.
BIRDVIEW_MAX_CHARS = 160

_FALLBACK_UNAVAILABLE = "Service temporarily unavailable. Please try again."


def normalize_ussd_code(raw: str | None) -> str:
    """Normalize dialled string for provider lookup only (not menu routing)."""
    code = (raw or "").strip()
    if not code:
        return ""
    if not code.startswith("*"):
        code = f"*{code.lstrip('*')}"
    if not code.endswith("#"):
        code = f"{code.rstrip('#')}#"
    return code


def normalize_birdview_input(raw: str | None) -> str | None:
    """Return the subscriber's latest keypress.

    Birdview's written contract says INPUT is never cumulative. In production we
    still receive AT-style trails such as ``1*0`` (see live SESSIONID logs).
    Always keep the segment after the last ``*`` so menu choice / Back / Home
    match what the handset just sent. Empty string stays empty (welcome).
    """
    if raw is None:
        return None
    text = str(raw).replace("\r", " ").replace("\n", " ").strip()
    if not text:
        return ""
    if "*" in text:
        text = text.split("*")[-1].strip()
    return text


def _casefold_map(data: dict[str, Any]) -> dict[str, str]:
    out: dict[str, str] = {}
    for key, value in data.items():
        if value is None:
            continue
        if isinstance(value, (list, tuple)):
            value = value[0] if value else ""
        out[str(key).strip().upper()] = str(value)
    return out


def extract_birdview_params(request: Request, body: bytes | None = None) -> dict[str, str]:
    """Merge query + optional body form fields; Birdview sends GET query params."""
    merged: dict[str, Any] = {}
    for key, value in request.query_params.multi_items():
        merged[key] = value
    if body:
        content_type = (request.headers.get("content-type") or "").lower()
        if "application/json" not in content_type:
            parsed = parse_qs(body.decode("utf-8", errors="replace"), keep_blank_values=True)
            for key, values in parsed.items():
                if key not in merged:
                    merged[key] = values[0] if values else ""
    return _casefold_map(merged)


def looks_like_birdview(request: Request, body: bytes | None = None) -> bool:
    params = extract_birdview_params(request, body)
    return bool(params.get("SESSIONID") and params.get("MSISDN"))


class BirdviewAdapter:
    kind = UssdProviderKind.BIRDVIEW.value

    async def authenticate(self, request: Request, settings: Any) -> None:
        """Optional shared secret / IP allowlist. Unset secret = open HTTPS callback."""
        allowed = list(getattr(settings, "allowed_ips", None) or [])
        if allowed:
            client = request.client.host if request.client else ""
            if client not in allowed:
                raise PermissionError("USSD callback IP is not allowed")

        expected = (getattr(settings, "auth_secret", None) or "").strip()
        if not expected:
            return
        header_name = (getattr(settings, "auth_header_name", None) or "X-USSD-Secret").strip()
        provided = (request.headers.get(header_name) or "").strip()
        if not provided or not hmac.compare_digest(provided, expected):
            raise PermissionError("Invalid USSD provider credentials")

    async def parse(self, request: Request, body: bytes | None = None) -> ProviderCallback:
        params = extract_birdview_params(request, body)
        session_id = (params.get("SESSIONID") or "").strip()
        msisdn = (params.get("MSISDN") or "").strip()
        # USSDCODE is informational for Birdview — used only to match our service record.
        ussd_code = normalize_ussd_code(params.get("USSDCODE"))
        # Empty INPUT => welcome screen for a new SESSIONID.
        # Live Birdview may still send cumulative ``a*b*c`` — normalize to latest.
        if "INPUT" in params:
            text = normalize_birdview_input(params.get("INPUT"))
        else:
            text = None

        if not session_id or not msisdn:
            raise ValueError("Birdview callback is missing SESSIONID or MSISDN")

        idem = (
            request.headers.get("X-Idempotency-Key")
            or f"bv:{session_id}:{params.get('INPUT') or ''}"
        )
        return ProviderCallback(
            provider_kind=self.kind,
            service_code=ussd_code,
            session_id=session_id,
            msisdn=msisdn,
            text=text,
            network_code=None,
            raw=dict(params),
            idempotency_key=str(idem)[:128],
        )

    def render(self, *, text: str, response_type: str) -> Response:
        clean = (text or "").strip()
        # Never let application text accidentally start with CON/END (would confuse Birdview).
        upper = clean.upper()
        if upper.startswith("CON ") or upper.startswith("END "):
            clean = clean[4:].lstrip()
        elif upper in {"CON", "END"}:
            clean = ""
        if len(clean) > BIRDVIEW_MAX_CHARS:
            clean = clean[: BIRDVIEW_MAX_CHARS - 1].rstrip() + "…"
        if not clean:
            clean = _FALLBACK_UNAVAILABLE
            response_type = UssdResponseType.END.value
        prefix = "END" if response_type == UssdResponseType.END.value else "CON"
        # Birdview: body must begin with CON or END; lines separated by \n.
        body = f"{prefix} {clean.replace('\r\n', '\n')}"
        return Response(
            content=body,
            status_code=200,
            media_type="text/plain; charset=utf-8",
            headers={"Cache-Control": "no-store"},
        )

    def render_unavailable(self) -> Response:
        return self.render(text=_FALLBACK_UNAVAILABLE, response_type=UssdResponseType.END.value)
