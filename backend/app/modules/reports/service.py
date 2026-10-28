"""Report generation — tenant-scoped aggregates only (no cross-tenant leakage)."""

from __future__ import annotations

from datetime import UTC, datetime
from typing import Any
from uuid import UUID

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database.enums import JobStatus, JobType
from app.core.exceptions import ValidationAppError
from app.core.security.branch_scope import apply_branch_predicate
from app.core.security.context import SecurityContext
from app.modules.audit.models import AuditEvent
from app.modules.audit.service import AuditService
from app.modules.customers.models import Customer
from app.modules.jobs.service import JobService
from app.modules.notifications.models import Notification
from app.modules.payments.models import Payment
from app.modules.policies.models import Policy
from app.modules.reports.enums import ReportStatus, ReportType
from app.modules.reports.models import ReportRun
from app.modules.reports.repository import ReportRepository
from app.modules.reports.schemas import ReportRunRequest


def to_public(row: ReportRun) -> dict[str, Any]:
    return {
        "id": str(row.id),
        "report_type": row.report_type,
        "status": row.status,
        "params": row.params_json,
        "result_summary": row.result_summary,
        "export_uri": row.export_uri,
        "failure_message": row.failure_message,
        "completed_at": row.completed_at,
        "job_id": row.job_id,
        "created_at": row.created_at,
        "updated_at": row.updated_at,
    }


class ReportService:
    def __init__(self, session: AsyncSession, ctx: SecurityContext) -> None:
        self.session = session
        self.ctx = ctx
        self.repo = ReportRepository(session, ctx)
        self.audit = AuditService(session)
        self.jobs = JobService(session, ctx)

    def available_types(self) -> list[str]:
        return [t.value for t in ReportType]

    async def list(
        self,
        *,
        page: int,
        limit: int,
        report_type: str | None,
        status: str | None,
    ) -> tuple[list[ReportRun], int]:
        return await self.repo.search(
            report_type=report_type,
            status=status,
            offset=(page - 1) * limit,
            limit=limit,
        )

    async def get(self, report_id: UUID) -> ReportRun:
        return await self.repo.get(report_id)

    async def run(self, body: ReportRunRequest) -> ReportRun:
        self.ctx.require_active_tenant()
        report_type = body.report_type.upper()
        if report_type not in {t.value for t in ReportType}:
            raise ValidationAppError(f"Unknown report type: {body.report_type}")

        job = await self.jobs.create(
            tenant_id=self.ctx.tenant_id,
            user_id=self.ctx.user_id,
            job_type=JobType.REPORT_GENERATION,
        )
        run = ReportRun(
            tenant_id=self.ctx.tenant_id,
            created_by_user_id=self.ctx.user_id,
            report_type=report_type,
            status=ReportStatus.RUNNING.value,
            params_json=body.params,
            job_id=job.job_key,
        )
        await self.repo.add(run)
        await self.session.flush()
        await self.jobs.transition(job, JobStatus.RUNNING)

        try:
            summary = await self._build_summary(report_type)
            run.result_summary = summary
            run.status = ReportStatus.COMPLETED.value
            run.completed_at = datetime.now(UTC)
            await self.session.flush()
            await self.jobs.transition(job, JobStatus.COMPLETED)
            await self.audit.record(
                action="report.completed",
                resource="report",
                resource_id=str(run.id),
                tenant_id=self.ctx.tenant_id,
                user_id=self.ctx.user_id,
                metadata={"report_type": report_type},
            )
        except Exception as exc:
            run.status = ReportStatus.FAILED.value
            run.failure_message = "Report generation failed"
            await self.session.flush()
            await self.jobs.transition(
                job, JobStatus.FAILED, error_code="REPORT_FAILED", error_message=str(exc)
            )
            raise
        return run

    async def _build_summary(self, report_type: str) -> dict[str, Any]:
        tid = self.ctx.tenant_id
        if report_type == ReportType.POLICIES_SUMMARY.value:
            total = int(
                await self.session.scalar(self._scoped_count(Policy, Policy.tenant_id == tid))
                or 0
            )
            by_status = await self._count_by(Policy, Policy.status, tid)
            return {"total": total, "by_status": by_status}

        if report_type == ReportType.PAYMENTS_SUMMARY.value:
            total = int(
                await self.session.scalar(self._scoped_count(Payment, Payment.tenant_id == tid))
                or 0
            )
            by_status = await self._count_by(Payment, Payment.status, tid)
            amount_stmt = apply_branch_predicate(
                select(func.coalesce(func.sum(Payment.amount), 0)).where(
                    Payment.tenant_id == tid, Payment.status == "SUCCESS"
                ),
                Payment,
                self.ctx,
            )
            amount = await self.session.scalar(amount_stmt)
            return {
                "total": total,
                "by_status": by_status,
                "successful_amount": str(amount or 0),
            }

        if report_type == ReportType.CUSTOMERS_SUMMARY.value:
            total = int(
                await self.session.scalar(
                    self._scoped_count(
                        Customer,
                        Customer.tenant_id == tid,
                        Customer.deleted_at.is_(None),
                    )
                )
                or 0
            )
            return {"total_active": total}

        if report_type == ReportType.NOTIFICATIONS_SUMMARY.value:
            total = int(
                await self.session.scalar(
                    self._scoped_count(Notification, Notification.tenant_id == tid)
                )
                or 0
            )
            by_status = await self._count_by(Notification, Notification.status, tid)
            by_channel = await self._count_by(Notification, Notification.channel, tid)
            return {"total": total, "by_status": by_status, "by_channel": by_channel}

        if report_type == ReportType.AUDIT_ACTIVITY.value:
            total = int(
                await self.session.scalar(
                    self._scoped_count(AuditEvent, AuditEvent.tenant_id == tid)
                )
                or 0
            )
            action_stmt = apply_branch_predicate(
                select(AuditEvent.action, func.count())
                .where(AuditEvent.tenant_id == tid)
                .group_by(AuditEvent.action)
                .order_by(func.count().desc())
                .limit(20),
                AuditEvent,
                self.ctx,
            )
            by_action_rows = (await self.session.execute(action_stmt)).all()
            return {
                "total": total,
                "top_actions": {str(a): int(c) for a, c in by_action_rows},
            }

        raise ValidationAppError(f"Unsupported report type: {report_type}")

    def _scoped_count(self, model: Any, *clauses: Any):
        stmt = select(func.count()).select_from(model)
        for clause in clauses:
            stmt = stmt.where(clause)
        return apply_branch_predicate(stmt, model, self.ctx)

    async def _count_by(self, model: Any, column: Any, tenant_id: UUID) -> dict[str, int]:
        stmt = apply_branch_predicate(
            select(column, func.count()).where(model.tenant_id == tenant_id).group_by(column),
            model,
            self.ctx,
        )
        rows = (await self.session.execute(stmt)).all()
        return {str(k): int(v) for k, v in rows}
