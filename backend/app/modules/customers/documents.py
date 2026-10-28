"""Private customer KYC document storage (logbook + national ID).

Relative key stored on customers.*_url columns:
  {tenant_id}/{customer_id}/{kind}/{sha256}.{ext}

Object location:
  local: data/customers/documents/{relative}
  gcs:   gs://{bucket}/{prefix}/customers/documents/{relative}
"""

from __future__ import annotations

import hashlib
from typing import Literal
from uuid import UUID

from app.core.config import get_settings
from app.core.exceptions import ValidationAppError
from app.core.security.filenames import sanitize_download_filename
from app.core.storage import get_blob_store

_NAMESPACE = "customers/documents"

CustomerDocKind = Literal["logbook", "id_front", "id_back"]
_KINDS = frozenset({"logbook", "id_front", "id_back"})
_MAX_NAME = 80


def detect_content_type(payload: bytes) -> str:
    if payload.startswith(b"%PDF"):
        return "application/pdf"
    if payload.startswith(b"\x89PNG\r\n\x1a\n"):
        return "image/png"
    if payload.startswith(b"\xff\xd8\xff"):
        return "image/jpeg"
    if payload.startswith(b"RIFF") and b"WEBP" in payload[:16]:
        return "image/webp"
    raise ValidationAppError("Unsupported file type. Use PDF, JPG, PNG, or WEBP.")


def store_customer_document(
    *,
    tenant_id: UUID,
    customer_id: UUID,
    kind: str,
    payload: bytes,
    filename: str,
) -> dict[str, str | int | bool]:
    if kind not in _KINDS:
        raise ValidationAppError("Unknown document type")
    settings = get_settings()
    limit = int(getattr(settings, "claims_document_max_bytes", 8_388_608) or 8_388_608)
    if len(payload) > limit:
        raise ValidationAppError("Document exceeds the maximum allowed size")
    if len(payload) < 16:
        raise ValidationAppError("Document is empty or too small")
    content_type = detect_content_type(payload)
    digest = hashlib.sha256(payload).hexdigest()
    ext = {
        "application/pdf": "pdf",
        "image/png": "png",
        "image/jpeg": "jpg",
        "image/webp": "webp",
    }[content_type]
    stored = f"{digest}.{ext}"
    relative = f"{tenant_id}/{customer_id}/{kind}/{stored}"
    result = get_blob_store().put(
        namespace=_NAMESPACE,
        relative_key=relative,
        data=payload,
        content_type=content_type,
        mode="overwrite",
    )
    # Stable API-facing locator (bucket stays private; downloads go through auth).
    public_url = f"customers/documents/{relative}"
    return {
        "kind": kind,
        "url": public_url,
        "storage_path": relative,
        "original_filename": sanitize_download_filename(
            filename, fallback=f"{kind}.{ext}"
        )[:_MAX_NAME],
        "content_type": content_type,
        "content_sha256": digest,
        "file_size_bytes": len(payload),
        "written": bool(result.written),
    }
