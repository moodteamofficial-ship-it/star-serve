"""Private object storage for certificates, mail PDFs, claim docs, and avatars.

Design (Cloud Run + GCS):
- Postgres stores *relative object keys* (never signed URLs, never absolute paths).
- Browser downloads stay on authenticated API routes (authz + audit preserved).
- Bucket stays non-public; only Cloud Run runtime SAs hold objectAdmin.
- Local backend uses the same key layout under ``data/`` for offline/dev.

Dedup:
- Default put mode is ``skip_identical`` — same key + same sha256 is a no-op.
- Use ``overwrite`` only for intentional replacements (e.g. profile avatars).
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Literal, Protocol

from app.core.config import get_settings

PutMode = Literal["skip_identical", "overwrite"]


@dataclass(frozen=True, slots=True)
class PutResult:
    key: str
    size_bytes: int
    sha256: str | None = None
    written: bool = True


class BlobStore(Protocol):
    def put(
        self,
        *,
        namespace: str,
        relative_key: str,
        data: bytes,
        content_type: str = "application/octet-stream",
        mode: PutMode = "skip_identical",
    ) -> PutResult: ...

    def get(self, *, namespace: str, relative_key: str) -> bytes | None: ...

    def exists(self, *, namespace: str, relative_key: str) -> bool: ...

    def delete(self, *, namespace: str, relative_key: str) -> None: ...


def object_key(namespace: str, relative_key: str, *, prefix: str | None = None) -> str:
    """Build a stable object key: ``[{prefix}/]{namespace}/{relative_key}``."""
    settings = get_settings()
    pref = (prefix if prefix is not None else (settings.gcs_prefix or "")).strip().strip("/")
    ns = (namespace or "").strip().strip("/")
    rel = (relative_key or "").strip().lstrip("/")
    if not ns or not rel:
        raise ValueError("namespace and relative_key are required")
    if ".." in rel.split("/") or rel.startswith("/"):
        raise ValueError("Invalid relative object key")
    parts = [p for p in (pref, ns, rel) if p]
    return "/".join(parts)


_STORE: BlobStore | None = None


def reset_blob_store() -> None:
    """Test helper — drop the cached backend."""
    global _STORE
    _STORE = None


def get_blob_store() -> BlobStore:
    global _STORE
    if _STORE is not None:
        return _STORE
    settings = get_settings()
    backend = (settings.storage_backend or "local").strip().lower()
    if backend == "gcs":
        from app.core.storage.gcs import GcsBlobStore

        _STORE = GcsBlobStore(
            bucket_name=(settings.gcs_bucket or "star_serve").strip(),
            prefix=(settings.gcs_prefix or "").strip(),
        )
    else:
        from app.core.storage.local import LocalBlobStore

        _STORE = LocalBlobStore(root_dir="data")
    return _STORE
