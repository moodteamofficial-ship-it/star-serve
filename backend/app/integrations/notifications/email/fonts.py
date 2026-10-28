"""Embed Poppins in HTML mail via @font-face (data URI).

Gmail strips <link> stylesheets and @import, so a Google Fonts URL never
applies there. Inlined @font-face is what Apple Mail, iOS Mail, Outlook.com,
Samsung Mail, and Thunderbird actually use.
"""

from __future__ import annotations

from base64 import b64encode
from functools import lru_cache
from pathlib import Path

_FONTS = Path(__file__).resolve().parents[3] / "assets" / "branding" / "fonts"

_FACES = (
    (400, "poppins-400-latin.woff2"),
    (600, "poppins-600-latin.woff2"),
    (700, "poppins-700-latin.woff2"),
)

_GSTATIC = {
    400: "https://fonts.gstatic.com/s/poppins/v24/pxiEyp8kv8JHgFVrJJfecnFHGPc.woff2",
    600: "https://fonts.gstatic.com/s/poppins/v24/pxiByp8kv8JHgFVrLEj6Z1xlFd2JQEk.woff2",
    700: "https://fonts.gstatic.com/s/poppins/v24/pxiByp8kv8JHgFVrLCz7Z1xlFd2JQEk.woff2",
}


@lru_cache(maxsize=1)
def poppins_font_face_css() -> str:
    blocks: list[str] = []
    for weight, filename in _FACES:
        try:
            raw = (_FONTS / filename).read_bytes()
        except OSError:
            raw = b""
        remote = _GSTATIC[weight]
        if raw:
            data = b64encode(raw).decode("ascii")
            src = (
                f"url(data:font/woff2;base64,{data}) format('woff2'),"
                f"url('{remote}') format('woff2')"
            )
        else:
            src = f"url('{remote}') format('woff2')"
        blocks.append(
            "@font-face{"
            "font-family:'Poppins';"
            "font-style:normal;"
            f"font-weight:{weight};"
            "font-display:swap;"
            f"src:{src};"
            "}"
        )
    return "".join(blocks)
