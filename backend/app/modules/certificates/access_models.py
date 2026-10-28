"""Append-only log of certificate file store / view / download events."""

from typing import Any

from sqlalchemy import ForeignKey, Integer, String, Text
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import Mapped, mapped_column

from app.core.database.base import Base, TimestampMixin, UUIDPrimaryKeyMixin


class CertificateFileAccess(Base, UUIDPrimaryKeyMixin, TimestampMixin):
    __tablename__ = "certificate_file_accesses"

    tenant_id: Mapped[Any] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("tenants.id", ondelete="RESTRICT"),
        nullable=False,
        index=True,
    )
    certificate_id: Mapped[Any] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("certificates.id", ondelete="RESTRICT"),
        nullable=False,
        index=True,
    )
    policy_id: Mapped[Any | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("policies.id", ondelete="SET NULL"), index=True
    )
    customer_id: Mapped[Any | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("customers.id", ondelete="SET NULL"), index=True
    )
    user_id: Mapped[Any | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("users.id", ondelete="SET NULL"), index=True
    )

    # STORED | VIEW | DOWNLOAD | OPEN_REMOTE | FETCH_FAILED
    access_kind: Mapped[str] = mapped_column(String(32), nullable=False, index=True)
    # local | remote_provider | system
    source: Mapped[str] = mapped_column(String(32), nullable=False, default="local")
    result: Mapped[str] = mapped_column(String(32), nullable=False, default="SUCCESS")

    local_file_path: Mapped[str | None] = mapped_column(String(512))
    provider_cert_url: Mapped[str | None] = mapped_column(Text)
    content_sha256: Mapped[str | None] = mapped_column(String(64))
    file_size_bytes: Mapped[int | None] = mapped_column(Integer)

    ip_address: Mapped[str | None] = mapped_column(String(64))
    user_agent: Mapped[str | None] = mapped_column(String(512))
    request_id: Mapped[str | None] = mapped_column(String(64), index=True)
    correlation_id: Mapped[str | None] = mapped_column(String(64), index=True)
    job_id: Mapped[str | None] = mapped_column(String(64))
    failure_message: Mapped[str | None] = mapped_column(Text)
    metadata_json: Mapped[dict[str, Any]] = mapped_column(
        "metadata", JSONB, nullable=False, default=dict
    )
