"""Report API schemas."""

from datetime import datetime
from typing import Any

from pydantic import BaseModel, Field


class ReportRunRequest(BaseModel):
    report_type: str = Field(max_length=64)
    params: dict[str, Any] = Field(default_factory=dict)

    model_config = {"extra": "forbid"}


class ReportPublic(BaseModel):
    id: str
    report_type: str
    status: str
    params: dict[str, Any]
    result_summary: dict[str, Any]
    export_uri: str | None
    failure_message: str | None
    completed_at: datetime | None
    job_id: str | None
    created_at: datetime
    updated_at: datetime

    model_config = {"extra": "forbid"}
