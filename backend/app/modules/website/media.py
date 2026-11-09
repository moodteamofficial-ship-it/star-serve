"""Public marketing media uploads (images only)."""

from __future__ import annotations

import hashlib
import re
from dataclasses import dataclass
from uuid import uuid4

from app.core.exceptions import ValidationAppError
from app.core.storage import get_blob_store

_NAMESPACE = "website_media"
_MAX_BYTES = 8_000_000
_SAFE_KEY = re.compile(r"^[a-f0-9-]{36}\.(jpg|jpeg|png|webp)$")


@dataclass(frozen=True, slots=True)
class StoredWebsiteMedia:
    relative_path: str
    content_type: str
    size_bytes: int
    public_path: str


def _detect_image_type(payload: bytes) -> tuple[str, str]:
    if payload.startswith(b"\xff\xd8\xff"):
        return "image/jpeg", "jpg"
    if payload.startswith(b"\x89PNG\r\n\x1a\n"):
        return "image/png", "png"
    if payload[:4] == b"RIFF" and payload[8:12] == b"WEBP":
        return "image/webp", "webp"
    raise ValidationAppError("Only JPEG, PNG or WebP images are allowed")


def store_website_media(payload: bytes) -> StoredWebsiteMedia:
    if not payload or len(payload) < 32:
        raise ValidationAppError("Image file is empty")
    if len(payload) > _MAX_BYTES:
        raise ValidationAppError("Image exceeds the 8 MB limit")
    content_type, ext = _detect_image_type(payload)
    relative = f"{uuid4()}.{ext}"
    store = get_blob_store()
    result = store.put(
        namespace=_NAMESPACE,
        relative_key=relative,
        data=payload,
        content_type=content_type,
        mode="overwrite",
    )
    _ = hashlib.sha256(payload).hexdigest()
    return StoredWebsiteMedia(
        relative_path=relative,
        content_type=content_type,
        size_bytes=result.size_bytes,
        public_path=f"/api/v1/website/media/{relative}",
    )


def read_website_media(relative_key: str) -> tuple[bytes, str] | None:
    key = (relative_key or "").strip().lstrip("/")
    if not _SAFE_KEY.match(key):
        return None
    store = get_blob_store()
    data = store.get(namespace=_NAMESPACE, relative_key=key)
    if data is None:
        return None
    if key.endswith(".png"):
        return data, "image/png"
    if key.endswith(".webp"):
        return data, "image/webp"
    return data, "image/jpeg"
