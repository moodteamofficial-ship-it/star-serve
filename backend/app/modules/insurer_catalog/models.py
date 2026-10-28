"""Insurer-wide quote catalog mirrored from the provider (Definite Assurance).

Not tenant data: every agency quotes against the same insurer catalog, so rows
are keyed by ``provider_code`` + the provider's own id. Rows are never deleted;
items the provider stops returning are marked ``is_active = false``.
"""

from datetime import datetime
from typing import Any

from sqlalchemy import (
    Boolean,
    DateTime,
    ForeignKey,
    Index,
    Integer,
    String,
    Text,
    UniqueConstraint,
)
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import Mapped, mapped_column

from app.core.database.base import Base, TimestampMixin, UUIDPrimaryKeyMixin


class InsurerCatalogCategory(Base, UUIDPrimaryKeyMixin, TimestampMixin):
    __tablename__ = "insurer_catalog_categories"
    __table_args__ = (
        UniqueConstraint(
            "provider_code", "name", name="uq_insurer_catalog_categories_provider_name"
        ),
    )

    provider_code: Mapped[str] = mapped_column(String(64), nullable=False)
    name: Mapped[str] = mapped_column(String(128), nullable=False)
    sort_order: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    product_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    is_active: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)


class InsurerCatalogProduct(Base, UUIDPrimaryKeyMixin, TimestampMixin):
    __tablename__ = "insurer_catalog_products"
    __table_args__ = (
        UniqueConstraint(
            "provider_code",
            "external_id",
            name="uq_insurer_catalog_products_provider_external",
        ),
        Index(
            "ix_insurer_catalog_products_listing",
            "provider_code",
            "is_active",
            "sort_order",
        ),
    )

    provider_code: Mapped[str] = mapped_column(String(64), nullable=False)
    external_id: Mapped[str] = mapped_column(String(64), nullable=False)
    code: Mapped[str] = mapped_column(String(64), nullable=False)
    name: Mapped[str] = mapped_column(String(255), nullable=False)
    description: Mapped[str | None] = mapped_column(Text)
    # Category as mapped from the provider payload (what the API returns per product).
    category: Mapped[str | None] = mapped_column(String(128))
    # Quote-wizard class after grouping rules (e.g. Tuk Tuk by name).
    category_id: Mapped[Any | None] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey(
            "insurer_catalog_categories.id",
            ondelete="SET NULL",
            name="fk_insurer_catalog_products_category",
        ),
        index=True,
    )
    sort_order: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    is_active: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)
    content_hash: Mapped[str] = mapped_column(String(64), nullable=False)
    raw: Mapped[dict[str, Any]] = mapped_column(JSONB, nullable=False, default=dict)
    first_seen_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    last_seen_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)


class InsurerCatalogCoverOption(Base, UUIDPrimaryKeyMixin, TimestampMixin):
    __tablename__ = "insurer_catalog_cover_options"
    __table_args__ = (
        UniqueConstraint(
            "product_id",
            "external_id",
            name="uq_insurer_catalog_cover_options_product_external",
        ),
    )

    product_id: Mapped[Any] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey(
            "insurer_catalog_products.id",
            ondelete="CASCADE",
            name="fk_insurer_catalog_cover_options_product",
        ),
        nullable=False,
        index=True,
    )
    external_id: Mapped[str] = mapped_column(String(64), nullable=False)
    name: Mapped[str] = mapped_column(String(255), nullable=False)
    sort_order: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    is_active: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)


class InsurerVehicleMake(Base, UUIDPrimaryKeyMixin, TimestampMixin):
    __tablename__ = "insurer_vehicle_makes"
    __table_args__ = (
        UniqueConstraint(
            "provider_code",
            "external_id",
            name="uq_insurer_vehicle_makes_provider_external",
        ),
        Index(
            "ix_insurer_vehicle_makes_listing",
            "provider_code",
            "is_active",
            "sort_order",
        ),
    )

    provider_code: Mapped[str] = mapped_column(String(64), nullable=False)
    external_id: Mapped[str] = mapped_column(String(64), nullable=False)
    code: Mapped[str] = mapped_column(String(64), nullable=False)
    name: Mapped[str] = mapped_column(String(128), nullable=False)
    sort_order: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    is_active: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)
    content_hash: Mapped[str] = mapped_column(String(64), nullable=False)
    first_seen_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    last_seen_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)


class InsurerVehicleModel(Base, UUIDPrimaryKeyMixin, TimestampMixin):
    __tablename__ = "insurer_vehicle_models"
    __table_args__ = (
        UniqueConstraint(
            "make_id", "external_id", name="uq_insurer_vehicle_models_make_external"
        ),
    )

    make_id: Mapped[Any] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey(
            "insurer_vehicle_makes.id",
            ondelete="CASCADE",
            name="fk_insurer_vehicle_models_make",
        ),
        nullable=False,
        index=True,
    )
    external_id: Mapped[str] = mapped_column(String(64), nullable=False)
    name: Mapped[str] = mapped_column(String(128), nullable=False)
    sort_order: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    is_active: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)


class InsurerCatalogSyncState(Base, TimestampMixin):
    """One row per provider: what we last stored and when we last checked."""

    __tablename__ = "insurer_catalog_sync_state"

    provider_code: Mapped[str] = mapped_column(String(64), primary_key=True)
    products_hash: Mapped[str | None] = mapped_column(String(64))
    makes_hash: Mapped[str | None] = mapped_column(String(64))
    product_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    make_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    model_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    last_attempt_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    last_success_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    last_changed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    last_error: Mapped[str | None] = mapped_column(Text)
    consecutive_failures: Mapped[int] = mapped_column(Integer, nullable=False, default=0)


class InsurerCatalogSyncRun(Base, UUIDPrimaryKeyMixin):
    __tablename__ = "insurer_catalog_sync_runs"
    __table_args__ = (
        Index("ix_insurer_catalog_sync_runs_provider_started", "provider_code", "started_at"),
    )

    provider_code: Mapped[str] = mapped_column(String(64), nullable=False)
    trigger: Mapped[str] = mapped_column(String(32), nullable=False)
    status: Mapped[str] = mapped_column(String(32), nullable=False)
    products_changed: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    makes_changed: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    product_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    make_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    model_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    duration_ms: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    error: Mapped[str | None] = mapped_column(Text)
    started_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    finished_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
