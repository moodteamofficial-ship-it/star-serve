"""Client IP resolution — never trust X-Forwarded-For unless explicitly enabled."""

from __future__ import annotations

import ipaddress

from starlette.requests import Request

from app.core.config import get_settings


def _xff_hops(request: Request) -> list[str]:
    return [
        part.strip()
        for part in (request.headers.get("x-forwarded-for") or "").split(",")
        if part.strip()
    ]


def _socket_peer(request: Request) -> str | None:
    if request.client and request.client.host:
        return (request.client.host or "")[:64] or None
    return None


def proxy_observed_ip(request: Request) -> str | None:
    """IP the immediate trusted edge observed (non-spoofable allowlist identity).

    When ``TRUST_X_FORWARDED_FOR`` is enabled, this is the *rightmost* XFF hop —
    the address appended by our platform proxy. Leftmost hops are
    client-controlled and must never authorize webhooks or lockouts alone.
    """
    settings = get_settings()
    if settings.trust_x_forwarded_for:
        hops = _xff_hops(request)
        if hops:
            return hops[-1][:64]
    return _socket_peer(request)


def end_user_ip(request: Request) -> str | None:
    """Best-effort end-user IP for guest session binding and soft rate limits.

    Cloud Run documents ``X-Forwarded-For`` as ``<client>, <platform-frontend>``.
    Extra reverse proxies (our SPA nginx → API) add further platform hops on the
    right. We peel ``TRUSTED_PROXY_HOPS`` addresses from the right and take the
    next hop — never the raw leftmost value alone (that remains spoofable).

    Example with ``TRUSTED_PROXY_HOPS=2`` behind SPA nginx + Cloud Run::

        spoof, client, web_gfe, api_gfe  →  client
    """
    settings = get_settings()
    if settings.trust_x_forwarded_for:
        hops = _xff_hops(request)
        if hops:
            peel = max(1, int(getattr(settings, "trusted_proxy_hops", 1) or 1))
            # Need peel platform hops on the right, plus one client hop.
            if len(hops) > peel:
                return hops[-(peel + 1)][:64]
            # Degenerate / short chain: prefer leftmost remaining over rightmost
            # platform hop so guest sessions stay stable across GFE changes.
            return hops[0][:64]
    return _socket_peer(request)


def client_ip(request: Request) -> str | None:
    """Caller IP for lockout, audit, allowlists, and rate limits.

    Defaults to :func:`proxy_observed_ip` (rightmost / socket peer) so callback
    allowlists and login lockouts cannot be steered by a forged leading XFF hop.
    """
    return proxy_observed_ip(request)


def ip_in_allowlist(ip: str | None, allowlist: str) -> bool:
    """Match a caller IP against a comma-separated list of addresses or CIDRs.

    An empty allowlist matches nothing — callers decide whether "not configured"
    means "skip the check", so this never silently allows everything.
    """
    entries = [entry.strip() for entry in (allowlist or "").split(",") if entry.strip()]
    if not entries or not ip:
        return False
    try:
        candidate = ipaddress.ip_address(ip)
    except ValueError:
        return False
    for entry in entries:
        try:
            if candidate in ipaddress.ip_network(entry, strict=False):
                return True
        except ValueError:
            continue
    return False
