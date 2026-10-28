"""Validate that a user id is a live principal in the caller's tenant."""

from __future__ import annotations

from uuid import UUID

from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database.enums import UserStatus
from app.core.exceptions import ValidationAppError
from app.modules.users.models import User


async def require_assignable_tenant_user(
    session: AsyncSession,
    *,
    tenant_id: UUID,
    user_id: UUID,
) -> User:
    user = await session.get(User, user_id)
    if (
        user is None
        or user.deleted_at is not None
        or user.tenant_id != tenant_id
        or user.status != UserStatus.ACTIVE.value
    ):
        raise ValidationAppError("Assigned user is not an active member of this tenant")
    return user
