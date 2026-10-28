"""Lucide-style badge icons for HTML mail.

Gmail-safe: opaque RGB PNG, CID-attached (never SVG or data URIs). Drawn at
4× then downsampled so strokes stay crisp at 40px.
"""

from __future__ import annotations

from functools import lru_cache
from io import BytesIO

from PIL import Image, ImageDraw

from app.integrations.notifications.email.branding import GREEN, WHITE

ICON_KINDS = ("mail", "phone", "clock", "info")

_SRC = 256
_OUT = 80
_PAD = 58
_STROKE = 14
_BADGE = GREEN
_GLYPH = WHITE
_CORNER = WHITE


def icon_cid(kind: str) -> str:
    return f"star-serve-icon-{kind}"


def _hex_rgb(value: str) -> tuple[int, int, int]:
    raw = value.removeprefix("#")
    return int(raw[0:2], 16), int(raw[2:4], 16), int(raw[4:6], 16)


def _pt(x: float, y: float) -> tuple[float, float]:
    scale = (_SRC - 2 * _PAD) / 24
    return _PAD + x * scale, _PAD + y * scale


def _box(x: float, y: float, w: float, h: float) -> tuple[float, float, float, float]:
    x0, y0 = _pt(x, y)
    x1, y1 = _pt(x + w, y + h)
    return x0, y0, x1, y1


def _cap(draw: ImageDraw.ImageDraw, x: float, y: float, width: int) -> None:
    r = width / 2
    draw.ellipse((x - r, y - r, x + r, y + r), fill=_hex_rgb(_GLYPH))


def _stroke_line(
    draw: ImageDraw.ImageDraw,
    a: tuple[float, float],
    b: tuple[float, float],
    width: int = _STROKE,
) -> None:
    color = _hex_rgb(_GLYPH)
    draw.line([a, b], fill=color, width=width)
    _cap(draw, a[0], a[1], width)
    _cap(draw, b[0], b[1], width)


def _stroke_poly(draw: ImageDraw.ImageDraw, points: list[tuple[float, float]]) -> None:
    for start, end in zip(points, points[1:], strict=False):
        _stroke_line(draw, start, end)


def _badge() -> tuple[Image.Image, ImageDraw.ImageDraw]:
    image = Image.new("RGB", (_SRC, _SRC), _hex_rgb(_CORNER))
    draw = ImageDraw.Draw(image)
    draw.ellipse((2, 2, _SRC - 3, _SRC - 3), fill=_hex_rgb(_BADGE))
    return image, draw


def _finish(image: Image.Image) -> bytes:
    sharp = image.resize((_OUT, _OUT), Image.Resampling.LANCZOS)
    buf = BytesIO()
    sharp.save(buf, format="PNG", optimize=True)
    return buf.getvalue()


def _mail() -> bytes:
    image, draw = _badge()
    draw.rounded_rectangle(
        _box(2, 5, 20, 14),
        radius=14,
        outline=_hex_rgb(_GLYPH),
        width=_STROKE,
    )
    _stroke_poly(draw, [_pt(3, 7.5), _pt(12, 13.2), _pt(21, 7.5)])
    return _finish(image)


def _phone() -> bytes:
    image, draw = _badge()
    draw.rounded_rectangle(
        _box(6.5, 2, 11, 20),
        radius=16,
        outline=_hex_rgb(_GLYPH),
        width=_STROKE,
    )
    cx, cy = _pt(12, 18.5)
    r = 5
    draw.ellipse((cx - r, cy - r, cx + r, cy + r), fill=_hex_rgb(_GLYPH))
    return _finish(image)


def _clock() -> bytes:
    image, draw = _badge()
    draw.ellipse(_box(2, 2, 20, 20), outline=_hex_rgb(_GLYPH), width=_STROKE)
    _stroke_line(draw, _pt(12, 12), _pt(12, 7))
    _stroke_line(draw, _pt(12, 12), _pt(16, 14))
    return _finish(image)


def _info() -> bytes:
    image, draw = _badge()
    draw.ellipse(_box(2, 2, 20, 20), outline=_hex_rgb(_GLYPH), width=_STROKE)
    cx, cy = _pt(12, 8)
    r = 6
    draw.ellipse((cx - r, cy - r, cx + r, cy + r), fill=_hex_rgb(_GLYPH))
    _stroke_line(draw, _pt(12, 12.2), _pt(12, 17), width=16)
    return _finish(image)


_DRAWERS = {
    "mail": _mail,
    "phone": _phone,
    "clock": _clock,
    "info": _info,
}


@lru_cache(maxsize=8)
def icon_png(kind: str) -> bytes:
    return _DRAWERS[kind]()
