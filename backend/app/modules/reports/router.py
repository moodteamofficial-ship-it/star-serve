"""Report HTTP routes."""

from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, Depends, Query, Request
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.dependencies.auth import get_db, require_permissions
from app.core.responses import success_response
from app.core.security.context import SecurityContext
from app.modules.reports.schemas import ReportPublic, ReportRunRequest
from app.modules.reports.service import ReportService, to_public
from app.modules.system_config.deps import require_system_service

router = APIRouter(prefix="/reports", tags=["Reports"])


@router.get("/types")
async def list_report_types(
    request: Request,
    db: Annotated[AsyncSession, Depends(get_db)],
    ctx: Annotated[SecurityContext, Depends(require_permissions("reports:read"))],
) -> dict:
    service = ReportService(db, ctx)
    return success_response(
        {"items": service.available_types()},
        request_id=getattr(request.state, "request_id", None),
    )


@router.get("")
async def list_reports(
    request: Request,
    db: Annotated[AsyncSession, Depends(get_db)],
    ctx: Annotated[SecurityContext, Depends(require_permissions("reports:read"))],
    page: Annotated[int, Query(ge=1, le=10_000)] = 1,
    limit: Annotated[int, Query(ge=1, le=100)] = 25,
    report_type: Annotated[str | None, Query(max_length=64)] = None,
    status: Annotated[str | None, Query(max_length=32)] = None,
) -> dict:
    service = ReportService(db, ctx)
    rows, total = await service.list(
        page=page, limit=limit, report_type=report_type, status=status
    )
    return success_response(
        {
            "items": [
                ReportPublic.model_validate(to_public(r)).model_dump(mode="json") for r in rows
            ],
            "page": page,
            "limit": limit,
            "total": total,
        },
        request_id=getattr(request.state, "request_id", None),
    )


@router.get("/{report_id}")
async def get_report(
    report_id: UUID,
    request: Request,
    db: Annotated[AsyncSession, Depends(get_db)],
    ctx: Annotated[SecurityContext, Depends(require_permissions("reports:read"))],
) -> dict:
    service = ReportService(db, ctx)
    row = await service.get(report_id)
    return success_response(
        ReportPublic.model_validate(to_public(row)).model_dump(mode="json"),
        request_id=getattr(request.state, "request_id", None),
        job_id=row.job_id,
    )


@router.post("")
async def run_report(
    body: ReportRunRequest,
    request: Request,
    db: Annotated[AsyncSession, Depends(get_db)],
    ctx: Annotated[SecurityContext, Depends(require_permissions("reports:run"))],
    _: Annotated[None, Depends(require_system_service("reports"))],
) -> dict:
    service = ReportService(db, ctx)
    row = await service.run(body)
    await db.commit()
    return success_response(
        ReportPublic.model_validate(to_public(row)).model_dump(mode="json"),
        message="Report completed",
        request_id=getattr(request.state, "request_id", None),
        job_id=row.job_id,
    )
