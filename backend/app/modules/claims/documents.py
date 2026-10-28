"""Private claim document storage — server-generated names, magic-byte checks.

Relative key stored in claim_documents.storage_path:
  {tenant_id}/{claim_id}/{sha256}.{ext}

Object location:
  local: data/claims/documents/{relative}
  gcs:   gs://{bucket}/{prefix}/claims/documents/{relative}

Keys are content-addressed within a claim so identical uploads share one object.
Legacy absolute filesystem paths are still readable for rows created before GCS.
"""

from __future__ import annotations

import hashlib
from pathlib import Path
from uuid import UUID

from app.core.config import get_settings
from app.core.exceptions import ValidationAppError
from app.core.security.filenames import sanitize_download_filename
from app.core.storage import get_blob_store

_NAMESPACE = "claims/documents"

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
    raise ValidationAppError("Unsupported file type")


def relative_claim_document_key(*, tenant_id: UUID, claim_id: UUID, stored_filename: str) -> str:
    name = (stored_filename or "").strip()
    if not name or "/" in name or ".." in name:
        raise ValidationAppError("Invalid stored filename")
    return f"{tenant_id}/{claim_id}/{name}"


def normalize_claim_storage_key(storage_path: str) -> str:
    """Accept relative keys or legacy absolute paths under data/claims/documents."""
    raw = (storage_path or "").strip().replace("\\", "/")
    if not raw:
        raise ValidationAppError("Invalid document path")
    marker = "/claims/documents/"
    if marker in raw:
        return raw.split(marker, 1)[1]
    if raw.startswith("data/claims/documents/"):
        return raw[len("data/claims/documents/") :]
    if raw.startswith("/") or ".." in raw.split("/"):
        raise ValidationAppError("Invalid document path")
    return raw.lstrip("/")


def store_claim_document(
    *,
    tenant_id: UUID,
    claim_id: UUID,
    payload: bytes,
    filename: str,
) -> dict[str, str | int | bool]:
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
    # Content-addressed leaf — identical bytes for a claim reuse one bucket object.
    stored = f"{digest}.{ext}"
    relative = relative_claim_document_key(
        tenant_id=tenant_id, claim_id=claim_id, stored_filename=stored
    )
    result = get_blob_store().put(
        namespace=_NAMESPACE,
        relative_key=relative,
        data=payload,
        content_type=content_type,
        mode="skip_identical",
    )
    return {
        "stored_filename": stored,
        "original_filename": sanitize_download_filename(
            filename, fallback=f"document.{ext}"
        )[:_MAX_NAME],
        "content_type": content_type,
        "content_sha256": digest,
        "file_size_bytes": len(payload),
        # Relative key only — never absolute disk paths or gs:// URIs in the DB.
        "storage_path": relative,
        "written": bool(result.written),
    }


def read_claim_document(storage_path: str) -> bytes:
    key = normalize_claim_storage_key(storage_path)
    content = get_blob_store().get(namespace=_NAMESPACE, relative_key=key)
    if content is not None:
        return content
    # Legacy absolute path fallback when still on local backend.
    path = Path(storage_path)
    if path.is_absolute() and path.is_file():
        root = Path(get_settings().claims_document_dir).expanduser()
        if not root.is_absolute():
            root = (Path.cwd() / root).resolve()
        else:
            root = root.resolve()
        resolved = path.resolve()
        if root in resolved.parents or resolved == root:
            return resolved.read_bytes()
    raise ValidationAppError("Document file is missing")
