"""Local filesystem BlobStore — mirrors gs://star_serve/{prefix}/… under data/."""

from __future__ import annotations

import hashlib
from pathlib import Path

from app.core.storage import PutMode, PutResult, object_key


class LocalBlobStore:
    def __init__(self, *, root_dir: str = "data") -> None:
        root = Path(root_dir).expanduser()
        if not root.is_absolute():
            root = (Path.cwd() / root).resolve()
        else:
            root = root.resolve()
        root.mkdir(parents=True, exist_ok=True)
        try:
            root.chmod(0o700)
        except OSError:
            pass
        self._root = root

    def _resolve(self, *, namespace: str, relative_key: str) -> Path:
        # Local layout skips env prefix so existing data/certificates paths keep working.
        key = object_key(namespace, relative_key, prefix="")
        absolute = (self._root / key).resolve()
        if not str(absolute).startswith(str(self._root)):
            raise ValueError("Object path escapes storage root")
        return absolute

    def put(
        self,
        *,
        namespace: str,
        relative_key: str,
        data: bytes,
        content_type: str = "application/octet-stream",
        mode: PutMode = "skip_identical",
    ) -> PutResult:
        _ = content_type
        digest = hashlib.sha256(data).hexdigest()
        path = self._resolve(namespace=namespace, relative_key=relative_key)
        key = object_key(namespace, relative_key, prefix="")

        if mode == "skip_identical" and path.is_file():
            try:
                existing = path.read_bytes()
            except OSError:
                existing = None
            if existing is not None and hashlib.sha256(existing).hexdigest() == digest:
                return PutResult(
                    key=key,
                    size_bytes=len(existing),
                    sha256=digest,
                    written=False,
                )

        path.parent.mkdir(parents=True, exist_ok=True)
        try:
            path.parent.chmod(0o700)
        except OSError:
            pass
        tmp = path.with_suffix(path.suffix + ".tmp")
        tmp.write_bytes(data)
        try:
            tmp.chmod(0o600)
        except OSError:
            pass
        tmp.replace(path)
        try:
            path.chmod(0o600)
        except OSError:
            pass
        return PutResult(
            key=key,
            size_bytes=len(data),
            sha256=digest,
            written=True,
        )

    def get(self, *, namespace: str, relative_key: str) -> bytes | None:
        try:
            path = self._resolve(namespace=namespace, relative_key=relative_key)
        except ValueError:
            return None
        if not path.is_file():
            return None
        return path.read_bytes()

    def exists(self, *, namespace: str, relative_key: str) -> bool:
        try:
            path = self._resolve(namespace=namespace, relative_key=relative_key)
        except ValueError:
            return False
        return path.is_file()

    def delete(self, *, namespace: str, relative_key: str) -> None:
        try:
            path = self._resolve(namespace=namespace, relative_key=relative_key)
        except ValueError:
            return
        if path.is_file():
            path.unlink()
