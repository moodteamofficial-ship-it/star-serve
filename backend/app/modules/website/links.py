"""Safe link resolution for CMS destinations."""

from __future__ import annotations

from urllib.parse import urlparse

from app.core.exceptions import ValidationAppError
from app.modules.website.enums import WebsiteLinkKind

QUOTE_BASE = "https://quote.starserveinsuranceagency.com/dashboard"

_PRODUCT_PATHS = {
    "motor-insurance": "/?product=motor",
    "medical-cover": "/?product=medical",
    "last-expense": "/?product=last-expense",
    "personal-accident": "/?product=personal-accident",
}


def resolve_link(kind: str, value: str) -> str:
    k = (kind or "").strip().lower()
    raw = (value or "").strip()
    if k == WebsiteLinkKind.INTERNAL.value:
        if not raw.startswith("/"):
            raise ValidationAppError("Internal links must start with /")
        return raw
    if k == WebsiteLinkKind.QUOTE.value:
        return raw or QUOTE_BASE + "/"
    if k == WebsiteLinkKind.QUOTE_PRODUCT.value:
        slug = raw.lstrip("/")
        suffix = _PRODUCT_PATHS.get(slug, "/")
        return QUOTE_BASE + suffix
    if k == WebsiteLinkKind.AGENT_REGISTER.value:
        return raw or QUOTE_BASE + "/register-agent"
    if k == WebsiteLinkKind.AGENT_LOGIN.value:
        return raw or QUOTE_BASE + "/login"
    if k == WebsiteLinkKind.PHONE.value:
        digits = "".join(ch for ch in raw if ch.isdigit() or ch == "+")
        return f"tel:{digits}" if digits else raw
    if k == WebsiteLinkKind.EMAIL.value:
        return f"mailto:{raw}" if "@" in raw else raw
    if k == WebsiteLinkKind.EXTERNAL.value:
        parsed = urlparse(raw)
        if parsed.scheme not in {"https", "http"}:
            raise ValidationAppError("External links must use http or https")
        return raw
    raise ValidationAppError(f"Unsupported link kind: {kind}")
