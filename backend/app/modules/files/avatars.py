"""Profile / subject media — stable keys, always overwrite on intentional update.

Layout:
  {tenant_id}/{subject_type}/{subject_id}.{ext}

``subject_type`` is ``user`` or ``customer``. Unlike certificates and claim docs,
avatars use ``mode=overwrite`` so a new upload replaces the previous object.
"""

from __future__ import annotations

import hashlib
import re
from dataclasses import dataclass
from uuid import UUID

from app.core.config import get_settings
from app.core.exceptions import ValidationAppError
from app.core.storage import PutResult, get_blob_store

_NAMESPACE = "avatars"
_UUID_RE = re.compile(
    r"^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$",
    re.IGNORECASE,
)
_SUBJECTS = frozenset({"user", "customer"})


def _avatar_max_bytes() -> int:
    return int(getattr(get_settings(), "avatar_max_bytes", 0) or 10_485_760)


@dataclass(frozen=True, slots=True)
class StoredAvatar:
    relative_path: str
    content_type: str
    sha256: str
    size_bytes: int
    written: bool


def _detect_image_type(payload: bytes) -> tuple[str, str]:
    if payload.startswith(b"\x89PNG\r\n\x1a\n"):
        return "image/png", "png"
    if payload.startswith(b"\xff\xd8\xff"):
        return "image/jpeg", "jpg"
    if payload.startswith(b"RIFF") and b"WEBP" in payload[:16]:
        return "image/webp", "webp"
    raise ValidationAppError("Avatar must be a PNG, JPEG, or WebP image")


def build_avatar_key(*, tenant_id: UUID | str, subject_type: str, subject_id: UUID | str) -> str:
    tenant = str(tenant_id).strip().lower()
    subject = str(subject_id).strip().lower()
    kind = (subject_type or "").strip().lower()
    if kind not in _SUBJECTS:
        raise ValidationAppError("Invalid avatar subject type")
    if not _UUID_RE.match(tenant) or not _UUID_RE.match(subject):
        raise ValidationAppError("Invalid avatar path identifiers")
    # Stable basename without extension segment — extension is part of leaf.
    return f"{tenant}/{kind}/{subject}"


def public_user_avatar_url(user_id: UUID | str, *, version: str) -> str:
    """Same-origin path for <img src> — cookies ride along on the dashboard host."""
    v = (version or "").strip().lower()[:16] or "1"
    return f"/api/v1/users/{user_id}/avatar?v={v}"


def store_avatar(
    *,
    tenant_id: UUID | str,
    subject_type: str,
    subject_id: UUID | str,
    payload: bytes,
) -> StoredAvatar:
    """Replace the subject's avatar object (intentional update — always overwrite)."""
    if not payload or len(payload) < 16:
        raise ValidationAppError("Avatar file is empty")
    if len(payload) > _avatar_max_bytes():
        raise ValidationAppError("Avatar exceeds the 10 MB limit")
    content_type, ext = _detect_image_type(payload)
    base = build_avatar_key(
        tenant_id=tenant_id, subject_type=subject_type, subject_id=subject_id
    )
    relative = f"{base}.{ext}"
    store = get_blob_store()
    # Drop other extensions for this subject so only one avatar object remains.
    for other in ("png", "jpg", "webp"):
        if other == ext:
            continue
        store.delete(namespace=_NAMESPACE, relative_key=f"{base}.{other}")
    result: PutResult = store.put(
        namespace=_NAMESPACE,
        relative_key=relative,
        data=payload,
        content_type=content_type,
        mode="overwrite",
    )
    return StoredAvatar(
        relative_path=relative,
        content_type=content_type,
        sha256=result.sha256 or hashlib.sha256(payload).hexdigest(),
        size_bytes=result.size_bytes,
        written=bool(result.written),
    )


def read_avatar(
    *,
    tenant_id: UUID | str,
    subject_type: str,
    subject_id: UUID | str,
) -> tuple[bytes, str] | None:
    base = build_avatar_key(
        tenant_id=tenant_id, subject_type=subject_type, subject_id=subject_id
    )
    store = get_blob_store()
    for ext, content_type in (
        ("jpg", "image/jpeg"),
        ("png", "image/png"),
        ("webp", "image/webp"),
    ):
        body = store.get(namespace=_NAMESPACE, relative_key=f"{base}.{ext}")
        if body is not None:
            return body, content_type
    return None
