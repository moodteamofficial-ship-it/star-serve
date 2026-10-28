"""Job lifecycle service."""

from datetime import UTC, datetime
from typing import Any
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database.enums import JobStatus, JobType
from app.core.exceptions import ResourceNotFoundError, TenantAccessError
from app.core.logging.context import get_correlation_id, get_request_id, new_job_id, set_job_id
from app.core.security.context import SecurityContext
from app.modules.jobs.models import Job, JobEvent


class JobService:
    def __init__(self, session: AsyncSession, ctx: SecurityContext | None = None) -> None:
        self.session = session
        self.ctx = ctx

    async def create(
        self,
        *,
        tenant_id: UUID,
        user_id: UUID | None,
        job_type: JobType | str = JobType.GENERIC,
        parent_job_id: UUID | None = None,
    ) -> Job:
        job_key = new_job_id()
        set_job_id(job_key)
        job = Job(
            job_key=job_key,
            tenant_id=tenant_id,
            user_id=user_id,
            job_type=str(job_type),
            status=JobStatus.CREATED.value,
            correlation_id=get_correlation_id(),
            request_id=get_request_id(),
            parent_job_id=parent_job_id,
        )
        self.session.add(job)
        await self.session.flush()
        await self.add_event(job, "JOB_CREATED", message="Job created")
        return job

    async def add_event(
        self,
        job: Job,
        event_type: str,
        *,
        message: str | None = None,
        metadata: dict[str, Any] | None = None,
    ) -> JobEvent:
        event = JobEvent(
            job_id=job.id,
            tenant_id=job.tenant_id,
            event_type=event_type,
            message=message,
            metadata_json=metadata or {},
        )
        self.session.add(event)
        await self.session.flush()
        return event

    async def transition(
        self,
        job: Job,
        status: JobStatus,
        *,
        error_code: str | None = None,
        error_message: str | None = None,
        progress: int | None = None,
    ) -> Job:
        job.status = status.value
        if progress is not None:
            job.progress = progress
        now = datetime.now(UTC)
        if status == JobStatus.RUNNING and job.started_at is None:
            job.started_at = now
        if status == JobStatus.COMPLETED:
            job.completed_at = now
            job.progress = 100
        if status == JobStatus.FAILED:
            job.failed_at = now
            job.last_error_code = error_code
            job.last_error_message = error_message
        if status == JobStatus.RETRYING:
            job.retry_count += 1
        await self.add_event(
            job,
            f"JOB_{status.value}",
            message=error_message,
            metadata={"error_code": error_code} if error_code else {},
        )
        return job

    async def get_for_tenant(self, job_key: str, tenant_id: UUID) -> Job:
        stmt = select(Job).where(Job.job_key == job_key, Job.tenant_id == tenant_id)
        job = await self.session.scalar(stmt)
        if job is None:
            raise ResourceNotFoundError()
        return job

    async def get_authorized(self, job_key: str) -> Job:
        if self.ctx is None:
            raise TenantAccessError()
        return await self.get_for_tenant(job_key, self.ctx.tenant_id)

    async def list_events(self, job: Job) -> list[JobEvent]:
        stmt = (
            select(JobEvent)
            .where(JobEvent.job_id == job.id, JobEvent.tenant_id == job.tenant_id)
            .order_by(JobEvent.created_at.asc())
        )
        result = await self.session.scalars(stmt)
        return list(result.all())
