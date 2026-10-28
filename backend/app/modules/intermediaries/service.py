"""Intermediary service — create/approve workflow with audit."""

from __future__ import annotations

import secrets
from dataclasses import replace
from datetime import UTC, datetime
from uuid import UUID

from sqlalchemy.ext.asyncio import AsyncSession

from app.core.exceptions import ValidationAppError
from app.core.logging import get_logger
from app.core.security.branch_scope import resolve_authorized_branch
from app.core.security.context import SecurityContext
from app.core.validation.identity import normalize_id_number, normalize_kra_pin, normalize_phone
from app.modules.audit.service import AuditService
from app.modules.intermediaries.login import AgentLoginService
from app.modules.intermediaries.models import Intermediary
from app.modules.intermediaries.repository import IntermediaryRepository
from app.modules.intermediaries.schemas import IntermediaryCreateRequest, IntermediaryUpdateRequest
from app.modules.intermediaries.uniqueness import agent_code_taken, ensure_unique_agent

logger = get_logger(__name__)


def to_public(row: Intermediary, *, login_status: str | None = None) -> dict:
    return {
        "id": str(row.id),
        "name": row.name,
        "email": row.email,
        "phone": row.phone,
        "identification": row.identification,
        "agent_code": row.agent_code,
        "kra_pin": row.kra_pin,
        "status": row.status,
        "branch_id": str(row.branch_id) if row.branch_id else None,
        "external_intermediary_ref": row.external_intermediary_ref,
        "approved_at": row.approved_at,
        "has_login": row.user_id is not None,
        "login_status": login_status if row.user_id is not None else None,
        "created_at": row.created_at,
        "updated_at": row.updated_at,
    }


class IntermediaryService:
    def __init__(self, session: AsyncSession, ctx: SecurityContext) -> None:
        self.session = session
        self.ctx = ctx
        self.audit = AuditService(session)

    async def _home_tenant_id(self) -> UUID:
        from app.core.security.ops_tenant import resolve_ops_tenant_id

        return await resolve_ops_tenant_id(self.session, self.ctx)

    async def _agency_ctx(self) -> SecurityContext:
        home = await self._home_tenant_id()
        if home == self.ctx.tenant_id:
            return self.ctx
        return replace(self.ctx, tenant_id=home)

    async def _agency_repo(self) -> tuple[SecurityContext, IntermediaryRepository]:
        scoped = await self._agency_ctx()
        return scoped, IntermediaryRepository(self.session, scoped)

    async def _allocate_agent_code(
        self, repo: IntermediaryRepository, preferred: str | None
    ) -> str:
        if preferred:
            return preferred
        for _ in range(48):
            code = f"{secrets.randbelow(1_000_000):06d}"
            if not await repo.find_by_agent_code(code) and not await agent_code_taken(
                self.session, code
            ):
                return code
        raise ValidationAppError("Could not allocate a unique agent code")

    async def create(self, body: IntermediaryCreateRequest) -> Intermediary:
        self.ctx.require_active_tenant()
        scoped, repo = await self._agency_repo()
        identification = normalize_id_number(body.identification)
        phone = normalize_phone(body.phone)
        email = str(body.email).lower()
        kra_pin = normalize_kra_pin(body.kra_pin)
        await ensure_unique_agent(
            self.session,
            {
                "identification": identification,
                "phone": phone,
                "email": email,
                "agent_code": body.agent_code,
                "kra_pin": kra_pin,
            },
        )

        logins = AgentLoginService(self.session, self.ctx)
        if body.password:
            await logins.assert_email_available(email)

        agent_code = await self._allocate_agent_code(repo, body.agent_code)
        branch_id = await resolve_authorized_branch(scoped, self.session, body.branch_id)
        row = Intermediary(
            tenant_id=scoped.tenant_id,
            branch_id=branch_id,
            created_by_user_id=self.ctx.user_id,
            name=body.name.strip(),
            email=email,
            phone=phone,
            identification=identification,
            agent_code=agent_code,
            kra_pin=kra_pin,
            status="PENDING",
            notes=body.notes,
        )
        await repo.add(row)
        await self.session.flush()
        await self.audit.record(
            action="intermediary.create",
            resource="intermediary",
            resource_id=str(row.id),
            tenant_id=scoped.tenant_id,
            user_id=self.ctx.user_id,
            metadata={"identification": row.identification, "agent_code": row.agent_code},
        )
        if body.password:
            await logins.provision(row, body.password)
        await self._notify_agent_kit(row, template_code="AGENT_REGISTERED")
        return row

    async def set_login(self, intermediary_id: UUID, password: str) -> Intermediary:
        """Create or reset the agent's login. It is usable only while the agent is approved."""
        self.ctx.require_active_tenant()
        scoped, repo = await self._agency_repo()
        row = await repo.get_active_by_id(intermediary_id)
        scoped.assert_branch_access(row.branch_id)
        await AgentLoginService(self.session, self.ctx).provision(row, password)
        return row

    async def login_statuses(self, rows: list[Intermediary]) -> dict[UUID, str]:
        user_ids = [row.user_id for row in rows if row.user_id is not None]
        if not user_ids:
            return {}
        from sqlalchemy import select

        from app.core.database.rls import set_rls_bypass
        from app.modules.users.models import User

        await set_rls_bypass(self.session, True)
        stmt = select(User.id, User.status).where(User.id.in_(user_ids))
        found = dict((await self.session.execute(stmt)).all())
        await set_rls_bypass(self.session, False)
        return {row.id: found[row.user_id] for row in rows if row.user_id in found}

    async def get(self, intermediary_id: UUID) -> Intermediary:
        _, repo = await self._agency_repo()
        return await repo.get_active_by_id(intermediary_id)

    async def list(
        self, *, page: int, limit: int, query: str | None, status: str | None
    ) -> tuple[list[Intermediary], int]:
        _, repo = await self._agency_repo()
        return await repo.search(
            query=query,
            status=status,
            offset=(page - 1) * limit,
            limit=limit,
        )

    async def update(
        self, intermediary_id: UUID, body: IntermediaryUpdateRequest
    ) -> Intermediary:
        self.ctx.require_active_tenant()
        scoped, repo = await self._agency_repo()
        row = await repo.get_active_by_id(intermediary_id)
        data = body.model_dump(exclude_unset=True)
        if "phone" in data and data["phone"] is not None:
            data["phone"] = normalize_phone(data["phone"])
        if "kra_pin" in data:
            data["kra_pin"] = normalize_kra_pin(data["kra_pin"])
        if "email" in data and data["email"] is not None:
            data["email"] = str(data["email"]).lower()
        if "branch_id" in data:
            if not data["branch_id"]:
                raise ValidationAppError("Branch is required")
            data["branch_id"] = await resolve_authorized_branch(
                scoped, self.session, data["branch_id"]
            )
        scoped.assert_branch_access(row.branch_id)
        await ensure_unique_agent(
            self.session,
            {key: data.get(key) for key in ("phone", "email", "kra_pin")},
            exclude_id=row.id,
        )
        for key, value in data.items():
            setattr(row, key, value)
        await self.session.flush()
        await AgentLoginService(self.session, self.ctx).sync_profile(row, set(data.keys()))
        await self.audit.record(
            action="intermediary.update",
            resource="intermediary",
            resource_id=str(row.id),
            tenant_id=scoped.tenant_id,
            user_id=self.ctx.user_id,
            metadata={"fields": sorted(data.keys())},
        )
        return row

    async def approve(self, intermediary_id: UUID) -> Intermediary:
        self.ctx.require_active_tenant()
        scoped, repo = await self._agency_repo()
        row = await repo.get_active_by_id(intermediary_id)
        if row.status == "APPROVED":
            return row
        if row.status not in {"PENDING", "REJECTED"}:
            raise ValidationAppError("Intermediary cannot be approved in its current state")
        row.status = "APPROVED"
        row.approved_at = datetime.now(UTC)
        row.approved_by_user_id = self.ctx.user_id
        await self.session.flush()
        await self.audit.record(
            action="intermediary.approve",
            resource="intermediary",
            resource_id=str(row.id),
            tenant_id=scoped.tenant_id,
            user_id=self.ctx.user_id,
        )
        await AgentLoginService(self.session, self.ctx).sync_status(row)
        await self._notify_agent_kit(row, template_code="AGENT_APPROVED")
        return row

    async def kit_channels(self, intermediary_id: UUID) -> list[str]:
        """Enabled notification channels that have a recipient on this agent."""
        _, repo = await self._agency_repo()
        row = await repo.get_active_by_id(intermediary_id)
        return await self._available_kit_channels(row)

    async def resend_kit(self, intermediary_id: UUID, channel: str) -> dict:
        """Queue the agent kit on one enabled channel. Raises if that channel cannot send."""
        self.ctx.require_active_tenant()
        scoped, repo = await self._agency_repo()
        row = await repo.get_active_by_id(intermediary_id)
        scoped.assert_branch_access(row.branch_id)
        available = await self._available_kit_channels(row)
        wanted = (channel or "").strip().upper()
        if wanted not in available:
            raise ValidationAppError(
                f"{wanted.title()} is not available for this agent right now"
            )
        template = (
            "AGENT_APPROVED" if str(row.status).upper() == "APPROVED" else "AGENT_REGISTERED"
        )
        queued = await self._notify_agent_kit(
            row, template_code=template, channels=[wanted], raise_on_failure=True
        )
        await self.audit.record(
            action="intermediary.resend_kit",
            resource="intermediary",
            resource_id=str(row.id),
            tenant_id=scoped.tenant_id,
            user_id=self.ctx.user_id,
            metadata={"channel": wanted, "template": template},
        )
        return {"channel": wanted, "queued": queued, "available": available}

    async def _available_kit_channels(self, row: Intermediary) -> list[str]:
        from app.modules.notifications.enums import NotificationChannel
        from app.modules.system_config.service import SystemConfigService

        cfg = SystemConfigService(self.session)
        email = (row.email or "").strip()
        phone = (row.phone or "").strip()
        candidates: list[tuple[str, bool]] = [
            (NotificationChannel.EMAIL.value, bool(email and "@" in email)),
            (NotificationChannel.SMS.value, bool(phone)),
            (NotificationChannel.WHATSAPP.value, bool(phone)),
        ]
        out: list[str] = []
        for channel, has_recipient in candidates:
            if not has_recipient:
                continue
            try:
                if await cfg.outbound_allowed(channel, live=True):
                    out.append(channel)
            except Exception:
                continue
        return out

    async def _notify_agent_kit(
        self,
        row: Intermediary,
        *,
        template_code: str,
        channels: list[str] | None = None,
        raise_on_failure: bool = False,
    ) -> list[str]:
        """Best-effort agent kit across enabled channels. Never blocks create/approve."""
        if not (row.agent_code or "").strip():
            return []
        from app.modules.intermediaries.agent_qr import agent_qr_url
        from app.modules.notifications.enums import NotificationChannel, NotificationTemplate
        from app.modules.notifications.service import NotificationService
        from app.modules.system_config.service import SystemConfigService

        code = (
            NotificationTemplate.AGENT_REGISTERED.value
            if template_code == NotificationTemplate.AGENT_REGISTERED.value
            else NotificationTemplate.AGENT_APPROVED.value
        )
        context = {
            "recipient_name": row.name,
            "agent_code": row.agent_code,
            "agent_link": agent_qr_url(row.agent_code),
        }
        scoped = await self._agency_ctx()
        notify = NotificationService(self.session, scoped)
        cfg = SystemConfigService(self.session)
        email = (row.email or "").strip()
        phone = (row.phone or "").strip()
        targets: list[tuple[str, str]] = []
        if email and "@" in email:
            targets.append((NotificationChannel.EMAIL.value, email))
        if phone:
            targets.append((NotificationChannel.SMS.value, phone))
            targets.append((NotificationChannel.WHATSAPP.value, phone))
        allowed = {c.upper() for c in channels} if channels is not None else None
        if allowed is not None:
            targets = [(ch, dest) for ch, dest in targets if ch in allowed]

        queued: list[str] = []
        for channel, recipient in targets:
            try:
                if not await cfg.outbound_allowed(channel, live=True):
                    if raise_on_failure and allowed is not None and channel in allowed:
                        raise ValidationAppError(
                            f"{channel.title()} notifications are switched off"
                        )
                    continue
                async with self.session.begin_nested():
                    result = await notify.enqueue_transactional(
                        channel=channel,
                        template_code=code,
                        recipient=recipient,
                        context=context,
                        related_resource="intermediary",
                        related_resource_id=row.id,
                        branch_id=row.branch_id,
                    )
                if result is not None:
                    queued.append(channel)
                elif raise_on_failure:
                    raise ValidationAppError(f"Could not queue {channel.title()} for this agent")
            except ValidationAppError:
                if raise_on_failure:
                    raise
                logger.warning(
                    "intermediary_agent_kit_notify_failed",
                    extra={
                        "intermediary_id": str(row.id),
                        "channel": channel,
                        "template": code,
                    },
                    exc_info=True,
                )
            except Exception:
                if raise_on_failure:
                    raise
                logger.warning(
                    "intermediary_agent_kit_notify_failed",
                    extra={
                        "intermediary_id": str(row.id),
                        "channel": channel,
                        "template": code,
                    },
                    exc_info=True,
                )
        return queued

    async def suspend(self, intermediary_id: UUID) -> Intermediary:
        self.ctx.require_active_tenant()
        scoped, repo = await self._agency_repo()
        row = await repo.get_active_by_id(intermediary_id)
        row.status = "SUSPENDED"
        await self.session.flush()
        await self.audit.record(
            action="intermediary.suspend",
            resource="intermediary",
            resource_id=str(row.id),
            tenant_id=scoped.tenant_id,
            user_id=self.ctx.user_id,
        )
        await AgentLoginService(self.session, self.ctx).sync_status(row)
        return row
