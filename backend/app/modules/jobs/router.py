"""Job lifecycle API — tenant scoped."""

from datetime import datetime
from typing import Annotated

from fastapi import APIRouter, Depends, Request
from pydantic import BaseModel
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database.enums import JobStatus
from app.core.dependencies.auth import get_db, require_permissions
from app.core.exceptions import ValidationAppError
from app.core.responses import success_response
from app.core.security.context import SecurityContext
from app.modules.jobs.service import JobService

router = APIRouter(prefix="/jobs", tags=["Jobs"])


class JobPublic(BaseModel):
    job_id: str
    job_type: str
    status: str
    progress: int
    created_at: datetime
    started_at: datetime | None
    completed_at: datetime | None
    failed_at: datetime | None
    retry_count: int
    last_error_code: str | None

    model_config = {"extra": "forbid"}


class JobEventPublic(BaseModel):
    event_type: str
    message: str | None
    created_at: datetime

    model_config = {"extra": "forbid"}


@router.get("/{job_id}")
async def get_job(
    job_id: str,
    request: Request,
    db: Annotated[AsyncSession, Depends(get_db)],
    ctx: Annotated[SecurityContext, Depends(require_permissions("job:read"))],
) -> dict:
    service = JobService(db, ctx)
    job = await service.get_authorized(job_id)
    return success_response(
        JobPublic(
            job_id=job.job_key,
            job_type=job.job_type,
            status=job.status,
            progress=job.progress,
            created_at=job.created_at,
            started_at=job.started_at,
            completed_at=job.completed_at,
            failed_at=job.failed_at,
            retry_count=job.retry_count,
            last_error_code=job.last_error_code,
        ).model_dump(),
        request_id=getattr(request.state, "request_id", None),
        job_id=job.job_key,
    )


@router.get("/{job_id}/events")
async def get_job_events(
    job_id: str,
    request: Request,
    db: Annotated[AsyncSession, Depends(get_db)],
    ctx: Annotated[SecurityContext, Depends(require_permissions("job:read"))],
) -> dict:
    service = JobService(db, ctx)
    job = await service.get_authorized(job_id)
    events = await service.list_events(job)
    return success_response(
        [
            JobEventPublic(
                event_type=e.event_type,
                message=e.message,
                created_at=e.created_at,
            ).model_dump()
            for e in events
        ],
        request_id=getattr(request.state, "request_id", None),
        job_id=job.job_key,
    )


@router.post("/{job_id}/cancel")
async def cancel_job(
    job_id: str,
    request: Request,
    db: Annotated[AsyncSession, Depends(get_db)],
    ctx: Annotated[SecurityContext, Depends(require_permissions("job:cancel"))],
) -> dict:
    service = JobService(db, ctx)
    job = await service.get_authorized(job_id)
    if job.status in {JobStatus.COMPLETED.value, JobStatus.CANCELLED.value}:
        raise ValidationAppError("Job cannot be cancelled in its current state")
    await service.transition(job, JobStatus.CANCELLED)
    await db.commit()
    return success_response(
        {"job_id": job.job_key, "status": job.status},
        message="Job cancelled",
        request_id=getattr(request.state, "request_id", None),
        job_id=job.job_key,
    )


@router.post("/{job_id}/retry")
async def retry_job(
    job_id: str,
    request: Request,
    db: Annotated[AsyncSession, Depends(get_db)],
    ctx: Annotated[SecurityContext, Depends(require_permissions("job:retry"))],
) -> dict:
    service = JobService(db, ctx)
    job = await service.get_authorized(job_id)
    # Financial job types must not be blindly retried — Phase 5 will refine.
    unsafe = {
        "PAYMENT_INITIATION",
        "PAYMENT_VERIFICATION",
        "WALLET_TOP_UP",
    }
    if job.job_type in unsafe:
        raise ValidationAppError("This job type cannot be retried automatically")
    if job.status not in {JobStatus.FAILED.value, JobStatus.EXPIRED.value}:
        raise ValidationAppError("Only failed or expired jobs can be retried")
    await service.transition(job, JobStatus.RETRYING)
    await service.transition(job, JobStatus.QUEUED)
    await db.commit()
    return success_response(
        {"job_id": job.job_key, "status": job.status, "retry_count": job.retry_count},
        message="Job queued for retry",
        request_id=getattr(request.state, "request_id", None),
        job_id=job.job_key,
    )
