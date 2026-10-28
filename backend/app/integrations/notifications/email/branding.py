"""Star Serve letterhead tokens for HTML mail — keep in sync with the product UI."""

from __future__ import annotations

from dataclasses import dataclass
from functools import lru_cache
from pathlib import Path

from app.core.config import Settings

# Match frontend/src/styles.css light tokens. Header art is the reception photo;
# the green wordmark PNG is only a fallback if that file is missing.
GREEN = "#30A82C"
GREEN_DEEP = "#248220"
NAVY = "#1B1464"
INK = "#141414"
MUTED = "#5C5C5C"
SOFT = "#E7F6E6"
LINE = "#E4E6E2"
LINE_STRONG = "#CFD3CC"
PAPER = "#F5F6F4"
SURFACE = "#F7F8F6"
WHITE = "#FFFFFF"
RADIUS = "16px"
RADIUS_SM = "8px"
CARD_WIDTH = 640

_LOGO = Path(__file__).resolve().parents[3] / "assets" / "branding" / "star-serve-logo.png"
_HEADER = Path(__file__).resolve().parents[3] / "assets" / "branding" / "star-serve-email-header.jpg"


@dataclass(frozen=True, slots=True)
class EmailBrand:
    product_name: str
    from_name: str
    from_address: str
    reply_to: str | None
    support_address: str
    app_url: str
    logo_url: str
    logo_cid: str
    logo_bytes: bytes | None
    header_url: str
    header_cid: str
    header_bytes: bytes | None
    support_phone: str = ""
    support_hours: str = ""
    legal_line: str = ""
    green: str = GREEN
    green_deep: str = GREEN_DEEP
    navy: str = NAVY
    ink: str = INK
    muted: str = MUTED
    soft: str = SOFT
    line: str = LINE
    line_strong: str = LINE_STRONG
    paper: str = PAPER
    surface: str = SURFACE
    white: str = WHITE
    radius: str = RADIUS
    radius_sm: str = RADIUS_SM
    card_width: int = CARD_WIDTH
    font_stack: str = (
        "'Poppins', Arial, Helvetica, sans-serif"
    )


def _read_bytes(path: Path) -> bytes | None:
    try:
        data = path.read_bytes()
    except OSError:
        return None
    return data or None


@lru_cache(maxsize=1)
def _logo_bytes() -> bytes | None:
    return _read_bytes(_LOGO)


@lru_cache(maxsize=1)
def _header_bytes() -> bytes | None:
    return _read_bytes(_HEADER)


def brand_from_settings(settings: Settings) -> EmailBrand:
    reply = (settings.email_reply_to or "").strip() or None
    support = (settings.email_support_address or settings.email_from_address).strip()
    remote = (settings.email_logo_url or "").strip()
    return EmailBrand(
        product_name=settings.app_name or "Star Serve",
        from_name=(settings.email_from_name or "Star Serve").strip(),
        from_address=(settings.email_from_address or "noreply@starserve.local").strip(),
        reply_to=reply,
        support_address=support,
        app_url=(settings.email_app_url or "http://localhost:5173").rstrip("/"),
        logo_url=remote,
        logo_cid="star-serve-logo",
        logo_bytes=None if remote else _logo_bytes(),
        header_url="",
        header_cid="star-serve-header",
        header_bytes=_header_bytes(),
        support_phone=(settings.email_support_phone or "").strip(),
        support_hours=(settings.email_support_hours or "").strip(),
        legal_line=(settings.email_legal_line or "").strip(),
    )
