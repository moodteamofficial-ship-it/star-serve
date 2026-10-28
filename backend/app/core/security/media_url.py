"""Public media URL allowlist — avatars are href/src values, not free text."""

from __future__ import annotations

import re
from ipaddress import ip_address
from urllib.parse import urlparse

from app.core.exceptions import ValidationAppError

_BLOCKED_HOSTS = frozenset(
    {"localhost", "127.0.0.1", "::1", "0.0.0.0", "[::1]"}
)

# Same-origin staff/customer avatar paths stored in DB and used as <img src>.
_SAME_ORIGIN_AVATAR_RE = re.compile(
    r"^/api/v1/(?:users|customers)/"
    r"[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}"
    r"/avatar(?:\?[A-Za-z0-9_.=&-]*)?$",
    re.IGNORECASE,
)


def sanitize_avatar_url(
    value: str | None,
    *,
    allowed_hosts: str = "",
) -> str | None:
    """Return a safe https URL, same-origin avatar path, or None.

    Reject javascript/data and private hosts. Allow ``/api/v1/users|customers/.../avatar``
    paths that the dashboard serves with cookie auth (not free-text absolute paths).
    """
    if value is None:
        return None
    text = str(value).strip()
    if not text:
        return None
    if text.startswith("/"):
        if _SAME_ORIGIN_AVATAR_RE.fullmatch(text):
            return text
        raise ValidationAppError("Avatar URL must be an https link")
    parsed = urlparse(text)
    if parsed.scheme != "https" or not parsed.hostname:
        raise ValidationAppError("Avatar URL must be an https link")
    if parsed.username or parsed.password:
        raise ValidationAppError("Avatar URL must be an https link")
    host = parsed.hostname.lower().rstrip(".")
    if host in _BLOCKED_HOSTS:
        raise ValidationAppError("Avatar URL host is not allowed")
    try:
        address = ip_address(host)
    except ValueError:
        address = None
    if address is not None and (
        address.is_private or address.is_loopback or address.is_link_local or address.is_reserved
    ):
        raise ValidationAppError("Avatar URL host is not allowed")
    patterns = [h.strip().lower().lstrip(".") for h in allowed_hosts.split(",") if h.strip()]
    if patterns and not any(host == pattern or host.endswith("." + pattern) for pattern in patterns):
        raise ValidationAppError("Avatar URL host is not allowed")
    return text
