"""Audit query helpers — append-only; never mutate events."""

from __future__ import annotations

from datetime import datetime
from typing import Any
from uuid import UUID

from sqlalchemy import func, or_, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.exceptions import ResourceNotFoundError
from app.core.security.context import SecurityContext
from app.modules.audit.models import AuditEvent
from app.modules.users.models import User


def to_public(row: AuditEvent, *, actor: User | None = None) -> dict[str, Any]:
    return {
        "id": str(row.id),
        "tenant_id": str(row.tenant_id) if row.tenant_id else None,
        "user_id": str(row.user_id) if row.user_id else None,
        "actor_name": actor.full_name if actor else None,
        "actor_email": actor.email if actor else None,
        "actor_avatar_url": actor.avatar_url if actor else None,
        "action": row.action,
        "resource": row.resource,
        "resource_id": row.resource_id,
        "result": row.result,
        "message": row.message,
        "metadata": row.metadata_json,
        "request_id": row.request_id,
        "job_id": row.job_id,
        "correlation_id": row.correlation_id,
        "ip_address": row.ip_address,
        "created_at": row.created_at,
    }


class AuditQueryService:
    def __init__(self, session: AsyncSession, ctx: SecurityContext) -> None:
        self.session = session
        self.ctx = ctx

    def _scoped(self):
        stmt = select(AuditEvent)
        if not self.ctx.is_platform_admin:
            stmt = stmt.where(AuditEvent.tenant_id == self.ctx.tenant_id)
        else:
            # Platform admins still default to their own tenant unless explicitly querying
            stmt = stmt.where(AuditEvent.tenant_id == self.ctx.tenant_id)
        return stmt

    async def _actors_by_id(self, rows: list[AuditEvent]) -> dict[UUID, User]:
        user_ids = {row.user_id for row in rows if row.user_id is not None}
        if not user_ids:
            return {}
        result = await self.session.scalars(select(User).where(User.id.in_(user_ids)))
        return {user.id: user for user in result.all()}

    async def list_public(
        self,
        *,
        page: int,
        limit: int,
        action: str | None,
        resource: str | None,
        query: str | None,
        since: datetime | None,
        until: datetime | None,
    ) -> tuple[list[dict[str, Any]], int]:
        rows, total = await self.list(
            page=page,
            limit=limit,
            action=action,
            resource=resource,
            query=query,
            since=since,
            until=until,
        )
        actors = await self._actors_by_id(rows)
        return [
            to_public(row, actor=actors.get(row.user_id) if row.user_id else None)
            for row in rows
        ], total

    async def get_public(self, event_id: UUID) -> dict[str, Any]:
        row = await self.get(event_id)
        actors = await self._actors_by_id([row])
        return to_public(row, actor=actors.get(row.user_id) if row.user_id else None)

    async def list(
        self,
        *,
        page: int,
        limit: int,
        action: str | None,
        resource: str | None,
        query: str | None,
        since: datetime | None,
        until: datetime | None,
    ) -> tuple[list[AuditEvent], int]:
        stmt = self._scoped()
        count_stmt = (
            select(func.count())
            .select_from(AuditEvent)
            .where(AuditEvent.tenant_id == self.ctx.tenant_id)
        )
        if action:
            stmt = stmt.where(AuditEvent.action == action)
            count_stmt = count_stmt.where(AuditEvent.action == action)
        if resource:
            stmt = stmt.where(AuditEvent.resource == resource)
            count_stmt = count_stmt.where(AuditEvent.resource == resource)
        if since:
            stmt = stmt.where(AuditEvent.created_at >= since)
            count_stmt = count_stmt.where(AuditEvent.created_at >= since)
        if until:
            stmt = stmt.where(AuditEvent.created_at <= until)
            count_stmt = count_stmt.where(AuditEvent.created_at <= until)
        if query:
            like = f"%{query.strip()}%"
            filt = or_(
                AuditEvent.action.ilike(like),
                AuditEvent.resource.ilike(like),
                AuditEvent.resource_id.ilike(like),
                AuditEvent.message.ilike(like),
            )
            stmt = stmt.where(filt)
            count_stmt = count_stmt.where(filt)
        total = int(await self.session.scalar(count_stmt) or 0)
        stmt = stmt.order_by(AuditEvent.created_at.desc()).offset((page - 1) * limit).limit(limit)
        return list((await self.session.scalars(stmt)).all()), total

    async def get(self, event_id: UUID) -> AuditEvent:
        stmt = self._scoped().where(AuditEvent.id == event_id)
        row = await self.session.scalar(stmt)
        if row is None:
            raise ResourceNotFoundError()
        return row
