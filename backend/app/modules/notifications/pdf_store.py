"""Durable PDFs for outbound mail and the stored-file registry.

Bytes live in local ``data/email-pdfs`` or ``gs://…/email-pdfs``.
Postgres keeps the relative key, checksum, creator, and access counts —
never an absolute path or signed URL.
"""

from __future__ import annotations

import hashlib
import re
from dataclasses import dataclass
from pathlib import Path
from uuid import UUID

from app.core.config import get_settings
from app.core.security.filenames import sanitize_download_filename
from app.core.storage import get_blob_store

_UUID_RE = re.compile(
    r"^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$",
    re.IGNORECASE,
)
_KIND_RE = re.compile(r"^(claim|certificate)$")
_PDF_MAGIC = b"%PDF"
_MAX_BYTES = 25 * 1024 * 1024
_KINDS = frozenset({"claim", "certificate"})
_NAMESPACE = "email-pdfs"


@dataclass(frozen=True, slots=True)
class StoredMailPdf:
    relative_path: str
    filename: str
    sha256: str
    size_bytes: int


def mail_pdf_root() -> Path:
    settings = get_settings()
    root = Path(settings.email_pdf_storage_dir).expanduser()
    if not root.is_absolute():
        root = (Path.cwd() / root).resolve()
    else:
        root = root.resolve()
    root.mkdir(parents=True, exist_ok=True)
    try:
        root.chmod(0o700)
    except OSError:
        pass
    return root


def _uuid(value: UUID | str, *, label: str) -> str:
    text = str(value).strip().lower()
    if not _UUID_RE.match(text):
        raise ValueError(f"Invalid {label} for mail PDF path")
    return text


def _kind(value: str) -> str:
    kind = (value or "").strip().lower()
    if kind not in _KINDS or not _KIND_RE.match(kind):
        raise ValueError("Invalid mail PDF kind")
    return kind


def validate_pdf_bytes(content: bytes) -> None:
    if not content:
        raise ValueError("Empty PDF payload")
    if len(content) > _MAX_BYTES:
        raise ValueError("PDF payload exceeds size limit")
    if not content.startswith(_PDF_MAGIC):
        raise ValueError("Payload is not a PDF")


def relative_mail_path(
    *,
    tenant_id: UUID | str,
    kind: str,
    resource_id: UUID | str,
) -> str:
    tenant = _uuid(tenant_id, label="tenant_id")
    resource = _uuid(resource_id, label="resource_id")
    return f"{tenant}/{_kind(kind)}/{resource}.pdf"


def _filename_sidecar_key(
    *,
    tenant_id: UUID | str,
    kind: str,
    resource_id: UUID | str,
) -> str:
    tenant = _uuid(tenant_id, label="tenant_id")
    resource = _uuid(resource_id, label="resource_id")
    return f"{tenant}/{_kind(kind)}/{resource}.filename"


def store_mail_pdf(
    *,
    tenant_id: UUID | str,
    kind: str,
    resource_id: UUID | str,
    content: bytes,
    filename: str,
) -> StoredMailPdf:
    validate_pdf_bytes(content)
    relative = relative_mail_path(
        tenant_id=tenant_id, kind=kind, resource_id=resource_id
    )
    store = get_blob_store()
    result = store.put(
        namespace=_NAMESPACE,
        relative_key=relative,
        data=content,
        content_type="application/pdf",
        mode="skip_identical",
    )
    safe_name = sanitize_download_filename(filename, fallback="document.pdf")
    store.put(
        namespace=_NAMESPACE,
        relative_key=_filename_sidecar_key(
            tenant_id=tenant_id, kind=kind, resource_id=resource_id
        ),
        data=safe_name.encode("utf-8"),
        content_type="text/plain; charset=utf-8",
        mode="skip_identical",
    )
    return StoredMailPdf(
        relative_path=relative,
        filename=safe_name,
        sha256=result.sha256 or hashlib.sha256(content).hexdigest(),
        size_bytes=result.size_bytes,
    )


def read_mail_pdf(
    *,
    tenant_id: UUID | str,
    kind: str,
    resource_id: UUID | str,
) -> tuple[bytes, str] | None:
    try:
        relative = relative_mail_path(
            tenant_id=tenant_id, kind=kind, resource_id=resource_id
        )
        sidecar = _filename_sidecar_key(
            tenant_id=tenant_id, kind=kind, resource_id=resource_id
        )
    except ValueError:
        return None
    store = get_blob_store()
    content = store.get(namespace=_NAMESPACE, relative_key=relative)
    if content is None:
        return None
    try:
        validate_pdf_bytes(content)
    except ValueError:
        return None
    filename = "document.pdf"
    name_bytes = store.get(namespace=_NAMESPACE, relative_key=sidecar)
    if name_bytes:
        raw = name_bytes.decode("utf-8", errors="replace").strip()
        filename = sanitize_download_filename(raw, fallback="document.pdf")
    return content, filename
