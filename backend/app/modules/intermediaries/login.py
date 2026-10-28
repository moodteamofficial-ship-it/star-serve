"""Agent login accounts: one Sales Agent user per intermediary.

The user lives on the agent's tenant and stays PENDING until the agent is
approved; suspending the agent disables the login and ends its sessions.
"""

from __future__ import annotations

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database.enums import RoleStatus, UserStatus
from app.core.database.rls import set_auth_write_gate, set_rls_bypass
from app.core.exceptions import ConflictError, ValidationAppError
from app.core.security.context import SecurityContext
from app.core.security.passwords import assert_password_strength, hash_password
from app.modules.audit.service import AuditService
from app.modules.auth.service import AuthService
from app.modules.intermediaries.models import Intermediary
from app.modules.roles.models import Role
from app.modules.roles.permissions_catalog import SALES_AGENT_ROLE_CODE
from app.modules.users.models import User, UserBranch

# A password reset never re-enables a login that staff disabled on the Users page.
_RESETTABLE_STATUSES = frozenset(
    {UserStatus.PENDING.value, UserStatus.ACTIVE.value, UserStatus.LOCKED.value}
)


def login_status_for(row: Intermediary) -> str:
    return UserStatus.ACTIVE.value if row.status == "APPROVED" else UserStatus.PENDING.value


class AgentLoginService:
    def __init__(self, session: AsyncSession, ctx: SecurityContext | None) -> None:
        self.session = session
        self.ctx = ctx
        # Public self-registration has no staff actor.
        self._actor_id = getattr(ctx, "user_id", None)
        self.auth = AuthService(session)
        self.audit = AuditService(session)

    async def assert_email_available(self, email: str, *, exclude_user_id=None) -> None:
        await set_rls_bypass(self.session, True)
        stmt = select(User.id).where(
            func.lower(User.email) == email.lower().strip(),
            User.deleted_at.is_(None),
        )
        if exclude_user_id is not None:
            stmt = stmt.where(User.id != exclude_user_id)
        existing = await self.session.scalar(stmt)
        await set_rls_bypass(self.session, False)
        if existing is not None:
            raise ConflictError("A user with this email already exists")

    async def _sales_agent_role(self, tenant_id) -> Role:
        await set_rls_bypass(self.session, True)
        role = await self.session.scalar(
            select(Role).where(
                Role.tenant_id == tenant_id,
                Role.code == SALES_AGENT_ROLE_CODE,
                Role.deleted_at.is_(None),
                Role.status == RoleStatus.ACTIVE.value,
            )
        )
        if role is None:
            raise ValidationAppError(
                "The Sales Agent role is missing or disabled. Enable it in Configuration → Roles."
            )
        return role

    async def provision(self, row: Intermediary, password: str) -> User:
        """Create the agent's login, or reset its password if one already exists."""
        assert_password_strength(password)
        user = await self._linked_user(row)
        if user is not None:
            await set_rls_bypass(self.session, True)
            await set_auth_write_gate(
                self.session, allow_auth_write=True, allow_status_write=True
            )
            user.password_hash = hash_password(password)
            user.failed_login_attempts = 0
            user.locked_until = None
            if user.status in _RESETTABLE_STATUSES:
                user.status = login_status_for(row)
            await self.session.flush()
            await set_auth_write_gate(
                self.session, allow_auth_write=False, allow_status_write=False
            )
            await set_rls_bypass(self.session, False)
            await self.auth.revoke_all_sessions(user.id, deleted_by=self._actor_id)
            await set_rls_bypass(self.session, False)
            await self._audit("intermediary.login_reset", row, user)
            return user

        await self.assert_email_available(row.email)
        role = await self._sales_agent_role(row.tenant_id)
        user = await self.auth.register_user(
            tenant_id=row.tenant_id,
            email=row.email,
            password=password,
            full_name=row.name,
            phone=row.phone,
            status=login_status_for(row),
            role_id=role.id,
        )
        await self.auth.assign_primary_role(user=user, role_id=role.id, tenant_id=row.tenant_id)
        await set_auth_write_gate(self.session, allow_auth_write=True, allow_status_write=True)
        if row.branch_id is not None:
            user.branch_id = row.branch_id
            self.session.add(
                UserBranch(tenant_id=row.tenant_id, user_id=user.id, branch_id=row.branch_id)
            )
        row.user_id = user.id
        await self.session.flush()
        await set_auth_write_gate(self.session, allow_auth_write=False, allow_status_write=False)
        await set_rls_bypass(self.session, False)
        await self._audit("intermediary.login_create", row, user)
        return user

    async def sync_status(self, row: Intermediary) -> None:
        """Approve → ACTIVE, anything else → PENDING/DISABLED, ending live sessions."""
        user = await self._linked_user(row)
        if user is None or user.status == UserStatus.DELETED.value:
            return
        if row.status == "APPROVED":
            target = UserStatus.ACTIVE.value
        elif row.status == "PENDING":
            target = UserStatus.PENDING.value
        else:
            target = UserStatus.DISABLED.value
        if user.status == target:
            return
        await set_rls_bypass(self.session, True)
        await set_auth_write_gate(self.session, allow_status_write=True)
        user.status = target
        if target == UserStatus.ACTIVE.value:
            user.locked_until = None
            user.failed_login_attempts = 0
        await self.session.flush()
        await set_auth_write_gate(self.session, allow_status_write=False)
        if target != UserStatus.ACTIVE.value:
            await self.auth.revoke_all_sessions(user.id, deleted_by=self._actor_id)
        await set_rls_bypass(self.session, False)

    async def sync_profile(self, row: Intermediary, fields: set[str]) -> None:
        """Keep the login's name/email/phone in step with the agent record."""
        user = await self._linked_user(row)
        if user is None or not fields & {"name", "email", "phone"}:
            return
        if "email" in fields and (user.email or "").lower() != row.email.lower():
            await self.assert_email_available(row.email, exclude_user_id=user.id)
        await set_rls_bypass(self.session, True)
        await set_auth_write_gate(self.session, allow_auth_write=True)
        user.full_name = row.name
        user.email = row.email.lower()
        user.phone = row.phone
        await self.session.flush()
        await set_auth_write_gate(self.session, allow_auth_write=False)
        await set_rls_bypass(self.session, False)

    async def login_status(self, row: Intermediary) -> str | None:
        user = await self._linked_user(row)
        return user.status if user is not None else None

    async def _linked_user(self, row: Intermediary) -> User | None:
        if row.user_id is None:
            return None
        await set_rls_bypass(self.session, True)
        user = await self.session.get(User, row.user_id)
        await set_rls_bypass(self.session, False)
        if user is None or user.deleted_at is not None:
            return None
        return user

    async def _audit(self, action: str, row: Intermediary, user: User) -> None:
        await self.audit.record(
            action=action,
            resource="intermediary",
            resource_id=str(row.id),
            tenant_id=row.tenant_id,
            user_id=self._actor_id,
            metadata={"login_user_id": str(user.id), "login_status": user.status},
        )
