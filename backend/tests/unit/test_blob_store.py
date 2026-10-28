"""Unit tests for the BlobStore key layout and local adapter."""

from __future__ import annotations

import hashlib
from uuid import uuid4

from app.core.storage import object_key, reset_blob_store
from app.core.storage.local import LocalBlobStore
from app.modules.claims.documents import store_claim_document
from app.modules.files.avatars import store_avatar


def test_object_key_layout(monkeypatch) -> None:
    from types import SimpleNamespace

    from app.core import storage as storage_mod

    monkeypatch.setattr(
        storage_mod,
        "get_settings",
        lambda: SimpleNamespace(gcs_prefix="staging"),
    )
    assert (
        object_key("certificates", "t/p/c.pdf")
        == "staging/certificates/t/p/c.pdf"
    )
    assert object_key("claims/documents", "t/c/f.pdf", prefix="") == "claims/documents/t/c/f.pdf"


def test_local_blob_roundtrip(tmp_path) -> None:
    reset_blob_store()
    store = LocalBlobStore(root_dir=str(tmp_path))
    tenant = uuid4()
    policy = uuid4()
    cert = uuid4()
    relative = f"{tenant}/{policy}/{cert}.pdf"
    payload = b"%PDF-1.4 hello"
    put = store.put(
        namespace="certificates",
        relative_key=relative,
        data=payload,
        content_type="application/pdf",
    )
    assert put.size_bytes == len(payload)
    assert put.sha256
    assert put.written is True
    assert store.exists(namespace="certificates", relative_key=relative)
    assert store.get(namespace="certificates", relative_key=relative) == payload
    assert (tmp_path / "certificates" / relative).is_file()


def test_skip_identical_does_not_rewrite(tmp_path) -> None:
    store = LocalBlobStore(root_dir=str(tmp_path))
    relative = f"{uuid4()}/{uuid4()}/{uuid4()}.pdf"
    payload = b"%PDF-1.4 same-bytes"
    first = store.put(
        namespace="certificates",
        relative_key=relative,
        data=payload,
        mode="skip_identical",
    )
    path = tmp_path / "certificates" / relative
    mtime = path.stat().st_mtime_ns
    second = store.put(
        namespace="certificates",
        relative_key=relative,
        data=payload,
        mode="skip_identical",
    )
    assert first.written is True
    assert second.written is False
    assert second.sha256 == first.sha256
    assert path.stat().st_mtime_ns == mtime


def test_skip_identical_rewrites_when_content_changes(tmp_path) -> None:
    store = LocalBlobStore(root_dir=str(tmp_path))
    relative = f"{uuid4()}/{uuid4()}/{uuid4()}.pdf"
    store.put(
        namespace="certificates",
        relative_key=relative,
        data=b"%PDF-1.4 v1",
        mode="skip_identical",
    )
    result = store.put(
        namespace="certificates",
        relative_key=relative,
        data=b"%PDF-1.4 v2-changed",
        mode="skip_identical",
    )
    assert result.written is True
    assert store.get(namespace="certificates", relative_key=relative) == b"%PDF-1.4 v2-changed"


def test_overwrite_always_writes(tmp_path) -> None:
    store = LocalBlobStore(root_dir=str(tmp_path))
    relative = f"{uuid4()}/user/{uuid4()}.jpg"
    payload = b"\xff\xd8\xff" + b"same" * 8
    first = store.put(
        namespace="avatars",
        relative_key=relative,
        data=payload,
        mode="overwrite",
    )
    second = store.put(
        namespace="avatars",
        relative_key=relative,
        data=payload,
        mode="overwrite",
    )
    assert first.written is True
    assert second.written is True


def test_claim_document_is_content_addressed(tmp_path, monkeypatch) -> None:
    reset_blob_store()
    monkeypatch.setenv("STORAGE_BACKEND", "local")
    from app.core import storage as storage_mod
    from app.modules.claims import documents as docs_mod

    store = LocalBlobStore(root_dir=str(tmp_path))
    monkeypatch.setattr(storage_mod, "get_blob_store", lambda: store)
    monkeypatch.setattr(docs_mod, "get_blob_store", lambda: store)

    tenant = uuid4()
    claim = uuid4()
    # Minimal valid JPEG-ish payload (>=16 bytes, jpeg magic)
    payload = b"\xff\xd8\xff" + (b"\x00" * 20)
    first = store_claim_document(
        tenant_id=tenant, claim_id=claim, payload=payload, filename="a.jpg"
    )
    second = store_claim_document(
        tenant_id=tenant, claim_id=claim, payload=payload, filename="b.jpg"
    )
    digest = hashlib.sha256(payload).hexdigest()
    assert first["content_sha256"] == digest
    assert first["storage_path"] == second["storage_path"]
    assert first["stored_filename"] == f"{digest}.jpg"
    assert second["written"] is False
    assert len(list((tmp_path / "claims" / "documents" / str(tenant) / str(claim)).iterdir())) == 1


def test_avatar_overwrite_replaces_previous_ext(tmp_path, monkeypatch) -> None:
    reset_blob_store()
    from app.core import storage as storage_mod
    from app.modules.files import avatars as avatars_mod

    store = LocalBlobStore(root_dir=str(tmp_path))
    monkeypatch.setattr(storage_mod, "get_blob_store", lambda: store)
    monkeypatch.setattr(avatars_mod, "get_blob_store", lambda: store)

    tenant = uuid4()
    user = uuid4()
    png = b"\x89PNG\r\n\x1a\n" + (b"\x00" * 20)
    jpg = b"\xff\xd8\xff" + (b"\x11" * 20)
    first = store_avatar(
        tenant_id=tenant, subject_type="user", subject_id=user, payload=png
    )
    second = store_avatar(
        tenant_id=tenant, subject_type="user", subject_id=user, payload=jpg
    )
    assert first.relative_path.endswith(".png")
    assert second.relative_path.endswith(".jpg")
    assert second.written is True
    folder = tmp_path / "avatars" / str(tenant) / "user"
    files = list(folder.iterdir())
    assert len(files) == 1
    assert files[0].name == f"{user}.jpg"
