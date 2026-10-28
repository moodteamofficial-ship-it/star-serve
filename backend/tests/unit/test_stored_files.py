"""Stored PDF registry never exposes absolute filesystem paths."""

from datetime import UTC, datetime
from types import SimpleNamespace
from uuid import uuid4

from app.modules.files.registry import to_public


def test_stored_file_public_omits_absolute_paths() -> None:
    row = SimpleNamespace(
        id=uuid4(),
        kind="claim",
        resource_id=uuid4(),
        filename="CLM-9.pdf",
        relative_path=f"{uuid4()}/claim/{uuid4()}.pdf",
        storage="email-pdfs",
        content_type="application/pdf",
        content_sha256="abc",
        file_size_bytes=12,
        created_by_user_id=uuid4(),
        created_by_label="Ada",
        source="staff",
        generate_count=2,
        view_count=4,
        download_count=1,
        email_count=1,
        last_generated_at=datetime.now(UTC),
        last_viewed_at=datetime.now(UTC),
        last_viewed_by_user_id=uuid4(),
        last_downloaded_at=None,
        last_downloaded_by_user_id=None,
        last_emailed_at=None,
        created_at=datetime.now(UTC),
        updated_at=datetime.now(UTC),
    )
    public = to_public(row)  # type: ignore[arg-type]
    blob = str(public)
    assert "/Users/" not in blob
    assert "backend/data" not in blob
    assert public["relative_path"] == row.relative_path
    assert public["view_count"] == 4
    assert public["created_by_label"] == "Ada"
    assert public["storage"] == "email-pdfs"
