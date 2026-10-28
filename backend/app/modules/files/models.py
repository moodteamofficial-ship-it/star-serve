"""Registry of PDFs stored under backend/data — relative keys only, never absolute paths."""

from datetime import datetime
from typing import Any

from sqlalchemy import DateTime, ForeignKey, Integer, String, Text, UniqueConstraint
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import Mapped, mapped_column

from app.core.database.base import Base, TimestampMixin, UUIDPrimaryKeyMixin
from app.modules.files.enums import StoredFileKind, StoredFileSource


class StoredFile(Base, UUIDPrimaryKeyMixin, TimestampMixin):
    """One row per (tenant, kind, resource) PDF copy on disk."""

    __tablename__ = "stored_files"
    __table_args__ = (
        UniqueConstraint(
            "tenant_id",
            "kind",
            "resource_id",
            name="uq_stored_files_tenant_kind_resource",
        ),
    )

    tenant_id: Mapped[Any] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("tenants.id", ondelete="RESTRICT"),
        nullable=False,
        index=True,
    )
    branch_id: Mapped[Any | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("branches.id", ondelete="SET NULL"), index=True
    )
    customer_id: Mapped[Any | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("customers.id", ondelete="SET NULL"), index=True
    )
    kind: Mapped[str] = mapped_column(
        String(32), nullable=False, default=StoredFileKind.CLAIM.value, index=True
    )
    resource_id: Mapped[Any] = mapped_column(UUID(as_uuid=True), nullable=False, index=True)
    # Relative to EMAIL_PDF_STORAGE_DIR, e.g. {tenant}/{kind}/{resource}.pdf
    relative_path: Mapped[str] = mapped_column(String(512), nullable=False)
    storage: Mapped[str] = mapped_column(String(32), nullable=False, default="email-pdfs")
    filename: Mapped[str] = mapped_column(String(128), nullable=False)
    content_type: Mapped[str] = mapped_column(String(64), nullable=False, default="application/pdf")
    content_sha256: Mapped[str] = mapped_column(String(64), nullable=False)
    file_size_bytes: Mapped[int] = mapped_column(Integer, nullable=False)

    created_by_user_id: Mapped[Any | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("users.id", ondelete="SET NULL"), index=True
    )
    created_by_label: Mapped[str | None] = mapped_column(String(255))
    source: Mapped[str] = mapped_column(
        String(32), nullable=False, default=StoredFileSource.STAFF.value
    )

    generate_count: Mapped[int] = mapped_column(Integer, nullable=False, default=1)
    view_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    download_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    email_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0)

    last_generated_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    last_generated_by_user_id: Mapped[Any | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("users.id", ondelete="SET NULL")
    )
    last_viewed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    last_viewed_by_user_id: Mapped[Any | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("users.id", ondelete="SET NULL")
    )
    last_downloaded_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    last_downloaded_by_user_id: Mapped[Any | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("users.id", ondelete="SET NULL")
    )
    last_emailed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))

    notes: Mapped[str | None] = mapped_column(Text)


class StoredFileAccess(Base, UUIDPrimaryKeyMixin, TimestampMixin):
    """Append-only view / download / email history for a stored PDF."""

    __tablename__ = "stored_file_accesses"

    tenant_id: Mapped[Any] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("tenants.id", ondelete="RESTRICT"),
        nullable=False,
        index=True,
    )
    stored_file_id: Mapped[Any] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("stored_files.id", ondelete="RESTRICT"),
        nullable=False,
        index=True,
    )
    resource_id: Mapped[Any] = mapped_column(UUID(as_uuid=True), nullable=False, index=True)
    user_id: Mapped[Any | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("users.id", ondelete="SET NULL"), index=True
    )
    actor_label: Mapped[str | None] = mapped_column(String(255))
    access_kind: Mapped[str] = mapped_column(String(32), nullable=False, index=True)
    source: Mapped[str] = mapped_column(String(32), nullable=False, default=StoredFileSource.STAFF.value)
    relative_path: Mapped[str | None] = mapped_column(String(512))
    content_sha256: Mapped[str | None] = mapped_column(String(64))
    file_size_bytes: Mapped[int | None] = mapped_column(Integer)
    ip_address: Mapped[str | None] = mapped_column(String(64))
    user_agent: Mapped[str | None] = mapped_column(String(512))
    request_id: Mapped[str | None] = mapped_column(String(64), index=True)
    metadata_json: Mapped[dict[str, Any]] = mapped_column(
        "metadata", JSONB, nullable=False, default=dict
    )
