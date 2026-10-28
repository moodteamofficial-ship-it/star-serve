"""Certificate PDF storage — relative keys in DB, bytes in local data/ or GCS.

Layout (relative key stored in certificates.local_file_path):
  {tenant_id}/{policy_id}/{certificate_id}.pdf

Object location:
  local: data/certificates/{relative}
  gcs:   gs://{bucket}/{prefix}/certificates/{relative}
"""

from __future__ import annotations

import hashlib
import re
from dataclasses import dataclass
from pathlib import Path
from uuid import UUID

from app.core.config import get_settings
from app.core.storage import get_blob_store

_UUID_RE = re.compile(
    r"^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$",
    re.IGNORECASE,
)
_PDF_MAGIC = b"%PDF"
_MAX_BYTES = 25 * 1024 * 1024
_NAMESPACE = "certificates"


@dataclass(frozen=True, slots=True)
class StoredCertificate:
    relative_path: str
    absolute_path: Path | None
    sha256: str
    size_bytes: int


def certificate_storage_root() -> Path:
    """Legacy local root — kept for tools/tests that still inspect the filesystem."""
    settings = get_settings()
    root = Path(settings.certificate_storage_dir).expanduser()
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


def _require_uuid(value: UUID | str, *, label: str) -> str:
    text = str(value).strip()
    if not _UUID_RE.match(text):
        raise ValueError(f"Invalid {label} for certificate path")
    return text.lower()


def build_relative_path(
    *,
    tenant_id: UUID | str,
    policy_id: UUID | str,
    certificate_id: UUID | str,
) -> str:
    tenant = _require_uuid(tenant_id, label="tenant_id")
    policy = _require_uuid(policy_id, label="policy_id")
    cert = _require_uuid(certificate_id, label="certificate_id")
    return f"{tenant}/{policy}/{cert}.pdf"


def validate_relative_path(relative_path: str) -> str:
    if not relative_path or relative_path.startswith("/") or ".." in relative_path.split("/"):
        raise ValueError("Invalid certificate relative path")
    parts = relative_path.split("/")
    if len(parts) != 3 or not parts[2].endswith(".pdf"):
        raise ValueError("Invalid certificate relative path shape")
    for segment in parts[:2]:
        if not _UUID_RE.match(segment):
            raise ValueError("Invalid certificate path segment")
    leaf = parts[2][:-4]
    if not _UUID_RE.match(leaf):
        raise ValueError("Invalid certificate filename")
    return relative_path


def resolve_absolute_path(relative_path: str) -> Path:
    """Resolve a stored relative path under the local storage root with traversal checks."""
    relative = validate_relative_path(relative_path)
    root = certificate_storage_root()
    absolute = (root / relative).resolve()
    if not str(absolute).startswith(str(root)):
        raise ValueError("Certificate path escapes storage root")
    return absolute


def validate_pdf_bytes(content: bytes) -> None:
    if not content:
        raise ValueError("Empty certificate payload")
    if len(content) > _MAX_BYTES:
        raise ValueError("Certificate payload exceeds size limit")
    if not content.startswith(_PDF_MAGIC):
        raise ValueError("Certificate payload is not a PDF")


def store_certificate_pdf(
    *,
    tenant_id: UUID | str,
    policy_id: UUID | str,
    certificate_id: UUID | str,
    content: bytes,
) -> StoredCertificate:
    validate_pdf_bytes(content)
    relative = build_relative_path(
        tenant_id=tenant_id,
        policy_id=policy_id,
        certificate_id=certificate_id,
    )
    result = get_blob_store().put(
        namespace=_NAMESPACE,
        relative_key=relative,
        data=content,
        content_type="application/pdf",
        mode="skip_identical",
    )
    absolute: Path | None = None
    if (get_settings().storage_backend or "local").strip().lower() != "gcs":
        try:
            absolute = resolve_absolute_path(relative)
        except ValueError:
            absolute = None
    return StoredCertificate(
        relative_path=relative,
        absolute_path=absolute,
        sha256=result.sha256 or hashlib.sha256(content).hexdigest(),
        size_bytes=result.size_bytes,
    )


def read_local_certificate(relative_path: str) -> bytes | None:
    try:
        relative = validate_relative_path(relative_path)
    except ValueError:
        return None
    content = get_blob_store().get(namespace=_NAMESPACE, relative_key=relative)
    if content is None:
        return None
    try:
        validate_pdf_bytes(content)
    except ValueError:
        return None
    return content


def local_copy_exists(relative_path: str | None) -> bool:
    if not relative_path:
        return False
    try:
        relative = validate_relative_path(relative_path)
    except ValueError:
        return False
    return get_blob_store().exists(namespace=_NAMESPACE, relative_key=relative)
