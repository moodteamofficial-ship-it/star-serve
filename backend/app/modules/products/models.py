"""Insurance reference data — products and vehicle makes.

Platform-global rows (tenant_id IS NULL) plus optional tenant overlays.
Synced from Definite Assurance in Phase 3; Phase 2 seeds local catalog.
"""

from datetime import datetime
from typing import Any

from sqlalchemy import Boolean, DateTime, Integer, String, Text, UniqueConstraint
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import Mapped, mapped_column

from app.core.database.base import Base, TimestampMixin, UUIDPrimaryKeyMixin


class InsuranceProduct(Base, UUIDPrimaryKeyMixin, TimestampMixin):
    __tablename__ = "insurance_products"
    __table_args__ = (
        UniqueConstraint("tenant_id", "code", name="uq_insurance_products_tenant_code"),
    )

    # NULL tenant_id = platform/shared reference catalog
    tenant_id: Mapped[Any | None] = mapped_column(UUID(as_uuid=True), index=True)
    code: Mapped[str] = mapped_column(String(64), nullable=False, index=True)
    name: Mapped[str] = mapped_column(String(255), nullable=False)
    description: Mapped[str | None] = mapped_column(Text)
    cover_options: Mapped[list[Any]] = mapped_column(
        JSONB, nullable=False, default=list
    )
    is_active: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)
    provider_code: Mapped[str | None] = mapped_column(String(64))
    metadata_json: Mapped[dict[str, Any]] = mapped_column(
        "metadata", JSONB, nullable=False, default=dict
    )
    synced_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))


class VehicleMake(Base, UUIDPrimaryKeyMixin, TimestampMixin):
    __tablename__ = "vehicle_makes"
    __table_args__ = (
        UniqueConstraint("tenant_id", "code", name="uq_vehicle_makes_tenant_code"),
    )

    tenant_id: Mapped[Any | None] = mapped_column(UUID(as_uuid=True), index=True)
    code: Mapped[str] = mapped_column(String(64), nullable=False, index=True)
    name: Mapped[str] = mapped_column(String(128), nullable=False)
    is_active: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)
    sort_order: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    provider_code: Mapped[str | None] = mapped_column(String(64))
    synced_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))


class CancellationReason(Base, UUIDPrimaryKeyMixin, TimestampMixin):
    __tablename__ = "cancellation_reasons"
    __table_args__ = (
        UniqueConstraint(
            "tenant_id", "code", name="uq_cancellation_reasons_tenant_code"
        ),
    )

    tenant_id: Mapped[Any | None] = mapped_column(UUID(as_uuid=True), index=True)
    code: Mapped[str] = mapped_column(String(64), nullable=False)
    label: Mapped[str] = mapped_column(String(255), nullable=False)
    is_active: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)
    provider_code: Mapped[str | None] = mapped_column(String(64))
