"""Branded agent QR card — same layout as the dashboard download (brandedAgentQr.ts)."""

from __future__ import annotations

import io
from functools import lru_cache
from pathlib import Path
from urllib.parse import quote, urlparse

import segno
from PIL import Image, ImageDraw, ImageFont

from app.core.config import get_settings

_BRANDING = Path(__file__).resolve().parents[2] / "assets" / "branding"
_LOGO = _BRANDING / "star-serve-logo.png"
_FONT_NAME = _BRANDING / "fonts" / "poppins-600-latin.woff2"
_FONT_CODE = _BRANDING / "fonts" / "poppins-700-latin.woff2"
_PUBLIC_QR_BASE = "https://quote.starserveinsuranceagency.com/dashboard"

# Card geometry in CSS px; rendered at 2x for print-sharp output at a mail-friendly size.
_SCALE = 2
_CARD_W = 720
_PAD_X = 56
_PAD_TOP = 52
_PAD_BOTTOM = 48
_LOGO_MAX_H = 96
_GAP_LOGO_QR = 30
_QR_SIZE = 440
_GAP_QR_CAPTION = 28
_NAME_SIZE = 28
_CODE_SIZE = 22
_CAPTION_GAP = 10
_PANEL_PAD = 14

_INK = (20, 20, 20)
_CODE_GREEN = (47, 107, 58)
_PANEL = (246, 247, 245)


def agent_qr_base_url() -> str:
    """Public welcome origin. Localhost is only for the SPA shell, never a printed QR."""
    base = (get_settings().email_app_url or "").strip().rstrip("/")
    host = (urlparse(base).hostname or "").lower()
    if not base or host in {"localhost", "127.0.0.1", "::1"}:
        return _PUBLIC_QR_BASE
    return base


def agent_qr_url(agent_code: str) -> str:
    return f"{agent_qr_base_url()}/#a={quote(agent_code.strip(), safe='')}"


def agent_qr_filename(agent_code: str) -> str:
    safe = "".join(ch for ch in agent_code if ch.isalnum()) or "agent"
    return f"StarServe-Agent-QR-{safe}.png"


def referral_qr_filename(referral_code: str) -> str:
    safe = "".join(ch for ch in referral_code if ch.isalnum()) or "referral"
    return f"StarServe-Referral-QR-{safe}.png"


def _font(path: Path, size: int) -> ImageFont.FreeTypeFont | ImageFont.ImageFont:
    try:
        return ImageFont.truetype(str(path), size)
    except OSError:
        return ImageFont.load_default(size=size)


@lru_cache(maxsize=1)
def _logo() -> Image.Image | None:
    try:
        with Image.open(_LOGO) as img:
            return img.convert("RGBA")
    except OSError:
        return None


def _truncate(draw: ImageDraw.ImageDraw, text: str, font, max_w: float) -> str:
    text = " ".join(text.split())
    if draw.textlength(text, font=font) <= max_w:
        return text
    while text and draw.textlength(f"{text}…", font=font) > max_w:
        text = text[:-1]
    return f"{text.rstrip()}…"


def build_agent_qr_card_png(
    *,
    agent_name: str,
    agent_code: str,
    payload_url: str | None = None,
    code_caption: str | None = None,
) -> bytes:
    s = _SCALE
    logo = _logo()
    logo_w = logo_h = 0
    if logo is not None:
        ratio = min((_CARD_W - _PAD_X * 2) / logo.width, _LOGO_MAX_H / logo.height)
        logo_w, logo_h = round(logo.width * ratio), round(logo.height * ratio)

    caption_h = _NAME_SIZE + _CAPTION_GAP + _CODE_SIZE
    card_h = (
        _PAD_TOP + logo_h + _GAP_LOGO_QR + _QR_SIZE + _GAP_QR_CAPTION + caption_h + _PAD_BOTTOM
    )
    card = Image.new("RGB", (_CARD_W * s, card_h * s), "white")
    draw = ImageDraw.Draw(card)
    draw.rectangle(
        (0, 0, _CARD_W * s - 1, card_h * s - 1), outline=(235, 235, 235), width=1
    )

    y = _PAD_TOP
    if logo is not None:
        scaled = logo.resize((logo_w * s, logo_h * s), Image.Resampling.LANCZOS)
        card.paste(scaled, (((_CARD_W - logo_w) // 2) * s, y * s), scaled)
    y += logo_h + _GAP_LOGO_QR

    qr_x = (_CARD_W - _QR_SIZE) // 2
    draw.rounded_rectangle(
        (
            (qr_x - _PANEL_PAD) * s,
            (y - _PANEL_PAD) * s,
            (qr_x + _QR_SIZE + _PANEL_PAD) * s,
            (y + _QR_SIZE + _PANEL_PAD) * s,
        ),
        radius=18 * s,
        fill=_PANEL,
    )
    qr_buf = io.BytesIO()
    segno.make(payload_url or agent_qr_url(agent_code), error="h").save(
        qr_buf, kind="png", scale=12, border=1, dark="#141414", light="#ffffff"
    )
    qr_buf.seek(0)
    with Image.open(qr_buf) as qr_img:
        qr = qr_img.convert("RGB").resize((_QR_SIZE * s, _QR_SIZE * s), Image.Resampling.NEAREST)
    card.paste(qr, (qr_x * s, y * s))
    y += _QR_SIZE + _GAP_QR_CAPTION

    name_font = _font(_FONT_NAME, _NAME_SIZE * s)
    code_font = _font(_FONT_CODE, _CODE_SIZE * s)
    name = _truncate(draw, agent_name or "Star Serve agent", name_font, (_CARD_W - _PAD_X * 2) * s)
    draw.text((_CARD_W * s / 2, y * s), name, font=name_font, fill=_INK, anchor="mt")
    y += _NAME_SIZE + _CAPTION_GAP
    draw.text(
        (_CARD_W * s / 2, y * s),
        (code_caption or f"Agent {agent_code.strip()}").strip(),
        font=code_font,
        fill=_CODE_GREEN,
        anchor="mt",
    )

    out = io.BytesIO()
    card.save(out, format="PNG", optimize=True)
    return out.getvalue()


def build_referral_qr_card_png(*, holder_name: str, referral_code: str) -> bytes:
    from app.modules.referrals.service import referral_link

    code = referral_code.strip()
    return build_agent_qr_card_png(
        agent_name=holder_name or "Star Serve customer",
        agent_code=code,
        payload_url=referral_link(code),
        code_caption=f"Referral {code}",
    )
