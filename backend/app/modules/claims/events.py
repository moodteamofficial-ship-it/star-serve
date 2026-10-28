"""Claim timeline + platform audit — written in the same transaction as the action."""

from __future__ import annotations

from typing import Any
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.logging.context import get_request_id
from app.core.security.context import SecurityContext
from app.modules.audit.service import AuditService
from app.modules.claims.enums import ClaimEventActorType
from app.modules.claims.models import ClaimEvent
from app.modules.users.models import User


async def actor_name(session: AsyncSession, user_id: UUID | None) -> str | None:
    if user_id is None:
        return None
    return await session.scalar(select(User.full_name).where(User.id == user_id))


class ClaimEventService:
    def __init__(self, session: AsyncSession, ctx: SecurityContext) -> None:
        self.session = session
        self.ctx = ctx
        self.audit = AuditService(session)

    async def record(
        self,
        *,
        claim_id: UUID,
        action: str,
        summary: str,
        previous_state: str | None = None,
        new_state: str | None = None,
        metadata: dict[str, Any] | None = None,
        actor_type: str | None = None,
        actor_user_id: UUID | None = None,
        actor_role: str | None = None,
        actor_display_name: str | None = None,
        ip_address: str | None = None,
        user_agent: str | None = None,
        tenant_id: UUID | None = None,
    ) -> ClaimEvent:
        user_id = actor_user_id if actor_user_id is not None else self.ctx.actor_user_id
        display = actor_display_name
        if display is None and user_id is not None:
            if user_id == self.ctx.actor_user_id and self.ctx.actor_display_name:
                display = self.ctx.actor_display_name
            else:
                display = await actor_name(self.session, user_id)
        if actor_type is None:
            if self.ctx.role_code == "webhook":
                actor_type = ClaimEventActorType.SYSTEM.value
            else:
                actor_type = ClaimEventActorType.USER.value
        event = ClaimEvent(
            tenant_id=self.ctx.tenant_id if tenant_id is None else tenant_id,
            claim_id=claim_id,
            actor_type=actor_type,
            actor_user_id=user_id,
            actor_role=actor_role or self.ctx.role_code,
            actor_display_name=display,
            action=action,
            summary=summary[:512],
            previous_state=previous_state,
            new_state=new_state,
            request_id=get_request_id(),
            ip_address=ip_address,
            user_agent=(user_agent or "")[:512] or None,
            metadata_json=metadata or {},
        )
        self.session.add(event)
        await self.audit.record(
            action=f"claim.{action.lower()}",
            resource="claim",
            resource_id=str(claim_id),
            tenant_id=event.tenant_id,
            user_id=user_id,
            ip_address=ip_address,
            user_agent=user_agent,
            message=summary,
            metadata={
                "previous_state": previous_state,
                "new_state": new_state,
                "role": event.actor_role,
                **(metadata or {}),
            },
            flush=False,
        )
        await self.session.flush()
        return event
