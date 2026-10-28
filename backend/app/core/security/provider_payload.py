"""Strip locators from insurer payloads before they leave the server."""

from __future__ import annotations

from typing import Any

_SENSITIVE_KEY_PARTS = (
    "url",
    "uri",
    "href",
    "sas",
    "blob",
    "download",
    "filepath",
    "file_path",
    "certurl",
    "certificateurl",
    "pdfurl",
    "storage",
)


def redact_provider_public(value: Any) -> Any:
    """Drop URL-like keys and https values from a provider JSON tree."""
    if isinstance(value, dict):
        out: dict[str, Any] = {}
        for key, item in value.items():
            lowered = str(key).lower().replace("-", "").replace("_", "")
            if any(part.replace("_", "") in lowered for part in _SENSITIVE_KEY_PARTS):
                continue
            if isinstance(item, str) and item.strip().lower().startswith(("http://", "https://")):
                continue
            out[key] = redact_provider_public(item)
        return out
    if isinstance(value, list):
        return [redact_provider_public(item) for item in value]
    return value
