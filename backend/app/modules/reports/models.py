"""Persisted report runs — aggregates stay tenant-scoped."""

from datetime import datetime
from typing import Any

from sqlalchemy import DateTime, String, Text
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import Mapped, mapped_column

from app.core.database.base import Base, TimestampMixin, UUIDPrimaryKeyMixin
from app.modules.reports.enums import ReportStatus


class ReportRun(Base, UUIDPrimaryKeyMixin, TimestampMixin):
    __tablename__ = "report_runs"

    tenant_id: Mapped[Any] = mapped_column(UUID(as_uuid=True), nullable=False, index=True)
    created_by_user_id: Mapped[Any | None] = mapped_column(UUID(as_uuid=True))
    report_type: Mapped[str] = mapped_column(String(64), nullable=False, index=True)
    status: Mapped[str] = mapped_column(
        String(32), nullable=False, default=ReportStatus.QUEUED.value, index=True
    )
    params_json: Mapped[dict[str, Any]] = mapped_column(
        "params", JSONB, nullable=False, default=dict
    )
    result_summary: Mapped[dict[str, Any]] = mapped_column(JSONB, nullable=False, default=dict)
    export_uri: Mapped[str | None] = mapped_column(String(512))
    failure_message: Mapped[str | None] = mapped_column(Text)
    completed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    job_id: Mapped[str | None] = mapped_column(String(64), index=True)
