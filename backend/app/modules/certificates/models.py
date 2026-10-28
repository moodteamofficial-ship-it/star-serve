"""Insurance certificate metadata — remote provider URL + local secure copy."""

from datetime import datetime
from typing import Any

from sqlalchemy import DateTime, ForeignKey, Integer, String, Text, UniqueConstraint
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import Mapped, mapped_column

from app.core.database.base import Base, TimestampMixin, UUIDPrimaryKeyMixin
from app.modules.payments.enums import CertificateStatus


class Certificate(Base, UUIDPrimaryKeyMixin, TimestampMixin):
    __tablename__ = "certificates"
    __table_args__ = (
        UniqueConstraint("tenant_id", "certificate_number", name="uq_certificates_tenant_number"),
    )

    tenant_id: Mapped[Any] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("tenants.id", ondelete="RESTRICT"),
        nullable=False,
        index=True,
    )
    policy_id: Mapped[Any] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("policies.id", ondelete="RESTRICT"),
        nullable=False,
        index=True,
    )
    payment_id: Mapped[Any | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("payments.id", ondelete="SET NULL"), index=True
    )
    customer_id: Mapped[Any | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("customers.id", ondelete="SET NULL"), index=True
    )
    generated_by_user_id: Mapped[Any | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("users.id", ondelete="SET NULL")
    )
    branch_id: Mapped[Any | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("branches.id", ondelete="SET NULL"), index=True
    )

    certificate_number: Mapped[str] = mapped_column(String(64), nullable=False, index=True)
    status: Mapped[str] = mapped_column(
        String(32), nullable=False, default=CertificateStatus.PENDING.value, index=True
    )
    external_certificate_ref: Mapped[str | None] = mapped_column(String(128))
    # Remote provider URL (Azure SAS, etc.) — kept for refresh; prefer local copy
    storage_key: Mapped[str | None] = mapped_column(Text)
    provider_cert_url: Mapped[str | None] = mapped_column(Text)
    # Relative path under CERTIFICATE_STORAGE_DIR, e.g.
    # {tenant_id}/{policy_id}/{certificate_id}.pdf
    local_file_path: Mapped[str | None] = mapped_column(String(512), index=True)
    local_stored_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    content_sha256: Mapped[str | None] = mapped_column(String(64))
    file_size_bytes: Mapped[int | None] = mapped_column(Integer)
    download_url_expires_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    generated_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    failure_message: Mapped[str | None] = mapped_column(Text)
    provider_payload: Mapped[dict[str, Any]] = mapped_column(JSONB, nullable=False, default=dict)
    job_id: Mapped[str | None] = mapped_column(String(64), index=True)
    correlation_id: Mapped[str | None] = mapped_column(String(64))
    request_id: Mapped[str | None] = mapped_column(String(64))
    last_accessed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    last_accessed_by_user_id: Mapped[Any | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("users.id", ondelete="SET NULL")
    )
    access_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
