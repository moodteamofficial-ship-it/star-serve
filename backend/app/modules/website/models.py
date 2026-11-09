"""Platform scoped marketing website persistence."""

from __future__ import annotations

from datetime import datetime
from typing import Any
from uuid import UUID

from sqlalchemy import Boolean, DateTime, Integer, String, Text, func
from sqlalchemy.dialects.postgresql import JSONB, UUID as PGUUID
from sqlalchemy.orm import Mapped, mapped_column

from app.core.database.base import Base, TimestampMixin, UUIDPrimaryKeyMixin


class WebsiteContentState(Base, UUIDPrimaryKeyMixin, TimestampMixin):
    """Singleton row — publish generation for cache busting."""

    __tablename__ = "website_content_state"

    content_version: Mapped[int] = mapped_column(Integer, nullable=False, default=1)
    last_published_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    last_published_by: Mapped[UUID | None] = mapped_column(PGUUID(as_uuid=True), nullable=True)


class WebsitePage(Base, UUIDPrimaryKeyMixin, TimestampMixin):
    __tablename__ = "website_pages"

    slug: Mapped[str] = mapped_column(String(64), unique=True, nullable=False)
    title: Mapped[str] = mapped_column(String(200), nullable=False)
    meta_title: Mapped[str | None] = mapped_column(String(120), nullable=True)
    meta_description: Mapped[str | None] = mapped_column(String(320), nullable=True)
    published: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)


class WebsiteSection(Base, UUIDPrimaryKeyMixin, TimestampMixin):
    __tablename__ = "website_sections"

    page_slug: Mapped[str] = mapped_column(String(64), nullable=False, index=True)
    section_key: Mapped[str] = mapped_column(String(64), nullable=False)
    section_type: Mapped[str] = mapped_column(String(32), nullable=False)
    sort_order: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    enabled: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)
    layout_variant: Mapped[str | None] = mapped_column(String(32), nullable=True)
    draft_content: Mapped[dict[str, Any]] = mapped_column(JSONB, nullable=False, default=dict)
    published_content: Mapped[dict[str, Any] | None] = mapped_column(JSONB, nullable=True)
    updated_by: Mapped[UUID | None] = mapped_column(PGUUID(as_uuid=True), nullable=True)


class WebsiteNavigationItem(Base, UUIDPrimaryKeyMixin, TimestampMixin):
    __tablename__ = "website_navigation_items"

    location: Mapped[str] = mapped_column(String(16), nullable=False, index=True)
    label: Mapped[str] = mapped_column(String(80), nullable=False)
    sort_order: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    link_kind: Mapped[str] = mapped_column(String(32), nullable=False)
    link_value: Mapped[str] = mapped_column(String(512), nullable=False)
    enabled: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)


class WebsiteEnquiry(Base, UUIDPrimaryKeyMixin):
    __tablename__ = "website_enquiries"

    full_name: Mapped[str] = mapped_column(String(120), nullable=False)
    phone: Mapped[str] = mapped_column(String(32), nullable=False)
    email: Mapped[str | None] = mapped_column(String(254), nullable=True)
    cover_needed: Mapped[str | None] = mapped_column(String(120), nullable=True)
    message: Mapped[str | None] = mapped_column(Text, nullable=True)
    status: Mapped[str] = mapped_column(String(16), nullable=False, default="NEW")
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )


class WebsiteAdminAudit(Base, UUIDPrimaryKeyMixin):
    __tablename__ = "website_admin_audit"

    actor_user_id: Mapped[UUID | None] = mapped_column(PGUUID(as_uuid=True), nullable=True)
    action: Mapped[str] = mapped_column(String(64), nullable=False)
    detail: Mapped[dict[str, Any]] = mapped_column(JSONB, nullable=False, default=dict)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
