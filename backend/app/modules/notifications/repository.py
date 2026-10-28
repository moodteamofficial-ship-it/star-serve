"""Tenant-scoped notification repository."""

from datetime import datetime
from uuid import UUID

from sqlalchemy import func, or_, select

from app.core.database.repository import TenantAwareRepository
from app.core.exceptions import ResourceNotFoundError
from app.modules.notifications.models import Notification


class NotificationRepository(TenantAwareRepository[Notification]):
    model = Notification

    async def get(self, notification_id: UUID) -> Notification:
        stmt = self._base_select().where(Notification.id == notification_id)
        row = await self.session.scalar(stmt)
        if row is None:
            raise ResourceNotFoundError()
        return row

    async def find_by_idempotency(self, key: str) -> Notification | None:
        stmt = self._base_select().where(Notification.idempotency_key == key)
        return await self.session.scalar(stmt)

    async def search(
        self,
        *,
        query: str | None,
        status: str | None,
        channel: str | None,
        offset: int,
        limit: int,
    ) -> tuple[list[Notification], int]:
        stmt = self._base_select()
        count_stmt = self._count_select()
        if status:
            stmt = stmt.where(Notification.status == status)
            count_stmt = count_stmt.where(Notification.status == status)
        if channel:
            stmt = stmt.where(Notification.channel == channel.upper())
            count_stmt = count_stmt.where(Notification.channel == channel.upper())
        if query:
            like = f"%{query.strip()}%"
            filt = or_(
                Notification.recipient.ilike(like),
                Notification.template_code.ilike(like),
                Notification.subject.ilike(like),
                Notification.provider_message_id.ilike(like),
            )
            stmt = stmt.where(filt)
            count_stmt = count_stmt.where(filt)
        total = int(await self.session.scalar(count_stmt) or 0)
        stmt = stmt.order_by(Notification.created_at.desc()).offset(offset).limit(limit)
        return list((await self.session.scalars(stmt)).all()), total

    async def count_since(self, *, since: datetime) -> int:
        stmt = (
            select(func.count())
            .select_from(Notification)
            .where(
                Notification.tenant_id == self.ctx.tenant_id,
                Notification.created_at >= since,
            )
        )
        return int(await self.session.scalar(stmt) or 0)
