"""Google Cloud Storage BlobStore — private bucket, ADC on Cloud Run."""

from __future__ import annotations

import hashlib
from functools import lru_cache

from app.core.storage import PutMode, PutResult, object_key

_SHA_META = "sha256"


@lru_cache(maxsize=1)
def _gcs_client():
    from google.cloud import storage

    return storage.Client()


class GcsBlobStore:
    """Writes to ``gs://{bucket}/[{prefix}/]{namespace}/{relative_key}``.

    Objects stay private (uniform bucket-level access + public access prevention).
    Auth uses Application Default Credentials — the Cloud Run runtime SA.

    Default put mode ``skip_identical`` avoids rewriting when object metadata
    (or bytes) already match the payload sha256.
    """

    def __init__(self, *, bucket_name: str, prefix: str = "") -> None:
        if not bucket_name:
            raise ValueError("GCS bucket name is required")
        self._bucket_name = bucket_name
        self._prefix = (prefix or "").strip().strip("/")

    def _blob(self, *, namespace: str, relative_key: str):
        client = _gcs_client()
        bucket = client.bucket(self._bucket_name)
        key = object_key(namespace, relative_key, prefix=self._prefix)
        return bucket.blob(key), key

    def _existing_sha256(self, blob) -> str | None:
        try:
            if not blob.exists():
                return None
            blob.reload()
            meta = blob.metadata or {}
            tagged = meta.get(_SHA_META)
            if isinstance(tagged, str) and len(tagged) == 64:
                return tagged.lower()
            # Legacy objects without metadata — compare bytes once.
            body = blob.download_as_bytes()
            return hashlib.sha256(body).hexdigest()
        except Exception:
            return None

    def put(
        self,
        *,
        namespace: str,
        relative_key: str,
        data: bytes,
        content_type: str = "application/octet-stream",
        mode: PutMode = "skip_identical",
    ) -> PutResult:
        digest = hashlib.sha256(data).hexdigest()
        blob, key = self._blob(namespace=namespace, relative_key=relative_key)

        if mode == "skip_identical":
            existing = self._existing_sha256(blob)
            if existing == digest:
                return PutResult(
                    key=key,
                    size_bytes=len(data),
                    sha256=digest,
                    written=False,
                )

        blob.metadata = {_SHA_META: digest}
        blob.upload_from_string(
            data,
            content_type=content_type or "application/octet-stream",
        )
        return PutResult(
            key=key,
            size_bytes=len(data),
            sha256=digest,
            written=True,
        )

    def get(self, *, namespace: str, relative_key: str) -> bytes | None:
        body = self._get_with_prefix(self._prefix, namespace=namespace, relative_key=relative_key)
        if body is not None:
            return body
        # Historical objects were written under staging/ before production prefix existed.
        if self._prefix == "production":
            return self._get_with_prefix("staging", namespace=namespace, relative_key=relative_key)
        return None

    def _get_with_prefix(
        self, prefix: str, *, namespace: str, relative_key: str
    ) -> bytes | None:
        try:
            client = _gcs_client()
            bucket = client.bucket(self._bucket_name)
            key = object_key(namespace, relative_key, prefix=prefix)
            blob = bucket.blob(key)
            if not blob.exists():
                return None
            return blob.download_as_bytes()
        except Exception:
            # Treat transport / permission / not-found as a soft miss so callers
            # can fall back to the provider URL and re-persist into the bucket.
            return None

    def exists(self, *, namespace: str, relative_key: str) -> bool:
        if self._exists_with_prefix(self._prefix, namespace=namespace, relative_key=relative_key):
            return True
        if self._prefix == "production":
            return self._exists_with_prefix(
                "staging", namespace=namespace, relative_key=relative_key
            )
        return False

    def _exists_with_prefix(self, prefix: str, *, namespace: str, relative_key: str) -> bool:
        try:
            client = _gcs_client()
            bucket = client.bucket(self._bucket_name)
            key = object_key(namespace, relative_key, prefix=prefix)
            return bool(bucket.blob(key).exists())
        except Exception:
            return False

    def delete(self, *, namespace: str, relative_key: str) -> None:
        blob, _key = self._blob(namespace=namespace, relative_key=relative_key)
        if blob.exists():
            blob.delete()
