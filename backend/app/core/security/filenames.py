"""Safe download filenames for Content-Disposition and similar headers."""

from __future__ import annotations

import re
import unicodedata

_DEFAULT_FILENAME = "certificate.pdf"
_MAX_FILENAME_LEN = 80
_UNSAFE = re.compile(r"[^A-Za-z0-9._-]+")


def sanitize_download_filename(
    raw: str | None,
    *,
    fallback: str = _DEFAULT_FILENAME,
    max_length: int = _MAX_FILENAME_LEN,
) -> str:
    """Return a header-safe basename. Never trust provider-controlled names.

    Strips CR/LF (header injection), path semantics, quotes, and other
    characters that can break or inject ``Content-Disposition``.
    """
    text = unicodedata.normalize("NFKC", str(raw or ""))
    text = text.split("\x00", 1)[0]
    text = text.split("\r", 1)[0].split("\n", 1)[0]
    text = text.replace("\\", "/").split("/")[-1]
    text = text.replace('"', "").replace("'", "").replace(";", "")
    text = text.strip().strip(".")
    text = _UNSAFE.sub("_", text).strip("._")
    if not text:
        text = fallback
    if "." not in text:
        text = f"{text}.pdf"
    if len(text) > max_length:
        stem, dot, suffix = text.rpartition(".")
        suffix = (suffix or "pdf")[:8]
        keep = max(8, max_length - len(suffix) - 1)
        text = f"{(stem or 'certificate')[:keep]}.{suffix}"
    if text in {".", ".."} or not text:
        return fallback
    return text


def content_disposition_header(disposition: str, filename: str | None) -> str:
    """Build a Content-Disposition value from an untrusted filename."""
    kind = "attachment" if disposition == "attachment" else "inline"
    safe = sanitize_download_filename(filename)
    return f'{kind}; filename="{safe}"'
