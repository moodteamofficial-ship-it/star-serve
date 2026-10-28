"""Platform reference catalogs — countries & currencies (soft-delete only)."""

from datetime import datetime
from typing import Any

from sqlalchemy import DateTime, ForeignKey, Integer, String
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column

from app.core.database.base import Base, SoftDeleteMixin, TimestampMixin, UUIDPrimaryKeyMixin


class Currency(Base, TimestampMixin, SoftDeleteMixin):
    __tablename__ = "currencies"

    code: Mapped[str] = mapped_column(String(8), primary_key=True)
    name: Mapped[str] = mapped_column(String(128), nullable=False)
    symbol: Mapped[str | None] = mapped_column(String(16))
    decimal_places: Mapped[int] = mapped_column(Integer, nullable=False, default=2)
    status: Mapped[str] = mapped_column(String(32), nullable=False, default="ACTIVE")


class Country(Base, UUIDPrimaryKeyMixin, TimestampMixin, SoftDeleteMixin):
    __tablename__ = "countries"

    iso2: Mapped[str] = mapped_column(String(2), nullable=False, unique=True)
    iso3: Mapped[str | None] = mapped_column(String(3))
    name: Mapped[str] = mapped_column(String(128), nullable=False)
    phone_code: Mapped[str | None] = mapped_column(String(8))
    currency_code: Mapped[str | None] = mapped_column(
        String(8),
        ForeignKey("currencies.code", ondelete="SET NULL"),
        index=True,
    )
    status: Mapped[str] = mapped_column(String(32), nullable=False, default="ACTIVE", index=True)
