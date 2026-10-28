"""User directory — create, list, and disable staff accounts."""

from __future__ import annotations

from uuid import UUID

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import get_settings
from app.core.database.enums import RoleStatus, UserStatus
from app.core.database.rls import set_auth_write_gate, set_rls_bypass
from app.core.exceptions import AuthorizationError, ConflictError, ValidationAppError
from app.core.security.branch_scope import BranchScope, resolve_authorized_branch
from app.core.security.context import SecurityContext
from app.core.security.media_url import sanitize_avatar_url
from app.core.security.passwords import hash_password
from app.core.validation.identity import normalize_phone
from app.modules.audit.service import AuditService
from app.modules.auth.service import AuthService
from app.modules.notifications.account_mail import notify_account_email
from app.modules.roles.models import Role
from app.modules.tenants.models import Branch
from app.modules.users.models import User, UserBranch
from app.modules.users.repository import UserRepository, UserRow
from app.modules.users.schemas import UserCreateRequest, UserUpdateRequest

_PROTECTED_ROLE_CODES = frozenset({"platform_admin", "agency_admin"})


def _public_avatar_url(value: str | None) -> str | None:
    if not value:
        return None
    try:
        return sanitize_avatar_url(value, allowed_hosts=get_settings().avatar_url_hosts)
    except ValidationAppError:
        return None


def to_public(row: UserRow) -> dict:
    user, role_name, role_code, branch_name, branch_code = row
    return {
        "id": str(user.id),
        "full_name": user.full_name,
        "email": user.email,
        "phone": user.phone,
        "status": user.status,
        "role_id": str(user.role_id) if user.role_id else None,
        "role_name": role_name,
        "role_code": role_code,
        "branch_id": str(user.branch_id) if user.branch_id else None,
        "branch_name": branch_name,
        "branch_code": branch_code,
        "avatar_url": _public_avatar_url(user.avatar_url),
        "last_login_at": user.last_login_at,
        "created_at": user.created_at,
        "updated_at": user.updated_at,
    }


class UserService:
    def __init__(self, session: AsyncSession, ctx: SecurityContext) -> None:
        self.session = session
        self.ctx = ctx
        self.repo = UserRepository(session, ctx)
        self.audit = AuditService(session)
        self.auth = AuthService(session)

    async def list_public(
        self, *, page: int, limit: int, query: str | None
    ) -> tuple[list[dict], int]:
        rows, total = await self.repo.search(
            query=query,
            offset=(page - 1) * limit,
            limit=limit,
        )
        return [to_public(row) for row in rows], total

    async def options(self) -> dict[str, list[dict]]:
        roles = await self._assignable_roles()
        branches = await self._assignable_branches()
        return {
            "roles": [
                {"id": str(role.id), "name": role.name, "code": role.code} for role in roles
            ],
            "branches": [
                {"id": str(branch.id), "name": branch.name, "code": branch.code}
                for branch in branches
            ],
        }

    async def create(self, body: UserCreateRequest) -> dict:
        self.ctx.require_active_tenant()
        self.ctx.require_permission("user:create")
        email = str(body.email).lower().strip()
        await self._assert_email_available(email)
        role = await self._require_assignable_role(body.role_id)
        branch_id = await resolve_authorized_branch(self.ctx, self.session, body.branch_id)
        phone = normalize_phone(body.phone) if body.phone and body.phone.strip() else None

        user = await self.auth.register_user(
            tenant_id=self.ctx.tenant_id,
            email=email,
            password=body.password,
            full_name=body.full_name,
            phone=phone,
            status=UserStatus.ACTIVE.value,
            role_id=role.id,
        )
        await self.auth.assign_primary_role(
            user=user, role_id=role.id, tenant_id=self.ctx.tenant_id
        )
        await set_auth_write_gate(self.session, allow_auth_write=True, allow_status_write=True)
        user.branch_id = branch_id
        existing = await self.session.scalar(
            select(UserBranch).where(
                UserBranch.user_id == user.id, UserBranch.branch_id == branch_id
            )
        )
        if existing is None:
            self.session.add(
                UserBranch(
                    tenant_id=self.ctx.tenant_id,
                    user_id=user.id,
                    branch_id=branch_id,
                )
            )
        await self.session.flush()
        await set_auth_write_gate(self.session, allow_auth_write=False, allow_status_write=False)
        await self.audit.record(
            action="user.create",
            resource="user",
            resource_id=str(user.id),
            tenant_id=self.ctx.tenant_id,
            user_id=self.ctx.user_id,
            metadata={"email": user.email, "role": role.code},
        )
        return await self._public_for(user)

    async def update(self, user_id: UUID, body: UserUpdateRequest) -> dict:
        self.ctx.require_active_tenant()
        self.ctx.require_permission("user:update")
        user = await self.repo.get_active_by_id(user_id)
        if user.is_platform_admin and not self.ctx.is_platform_admin:
            raise AuthorizationError()

        password_changed = bool(body.password)
        account_changed = any(
            value is not None
            for value in (body.full_name, body.email, body.phone, body.branch_id, body.role_id)
        )
        if body.full_name is not None:
            user.full_name = body.full_name
        if body.email is not None:
            email = str(body.email).lower().strip()
            if email != (user.email or "").lower():
                await self._assert_email_available(email)
            user.email = email
        if body.phone is not None:
            user.phone = normalize_phone(body.phone) if body.phone.strip() else None
        if body.branch_id is not None:
            branch_id = await resolve_authorized_branch(self.ctx, self.session, body.branch_id)
            user.branch_id = branch_id
            existing = await self.session.scalar(
                select(UserBranch).where(
                    UserBranch.user_id == user.id, UserBranch.branch_id == branch_id
                )
            )
            if existing is None:
                self.session.add(
                    UserBranch(
                        tenant_id=self.ctx.tenant_id,
                        user_id=user.id,
                        branch_id=branch_id,
                    )
                )
        if body.role_id is not None and body.role_id != user.role_id:
            if user.id == self.ctx.user_id:
                raise ValidationAppError("You cannot change your own role")
            role = await self._require_assignable_role(body.role_id)
            await self.auth.assign_primary_role(
                user=user, role_id=role.id, tenant_id=self.ctx.tenant_id
            )
        if body.password:
            await set_auth_write_gate(self.session, allow_auth_write=True)
            user.password_hash = hash_password(body.password)
            await set_auth_write_gate(self.session, allow_auth_write=False)
        await self.session.flush()
        await self.audit.record(
            action="user.update",
            resource="user",
            resource_id=str(user.id),
            tenant_id=self.ctx.tenant_id,
            user_id=self.ctx.user_id,
            metadata={"email": user.email},
        )
        if password_changed:
            await notify_account_email(
                self.session,
                user,
                template="ACCOUNT_PASSWORD_CHANGED",
                ctx=self.ctx,
            )
        elif account_changed:
            await notify_account_email(
                self.session,
                user,
                template="ACCOUNT_UPDATED",
                ctx=self.ctx,
                context={"detail": "Profile details on this account were changed."},
            )
        return await self._public_for(user)

    async def set_status(self, user_id: UUID, status: str) -> dict:
        self.ctx.require_active_tenant()
        self.ctx.require_permission("user:disable")
        if user_id == self.ctx.user_id:
            raise ValidationAppError("You cannot change your own status")
        user = await self.repo.get_active_by_id(user_id)
        if user.is_platform_admin and not self.ctx.is_platform_admin:
            raise AuthorizationError()
        await set_auth_write_gate(self.session, allow_status_write=True)
        user.status = status
        await self.session.flush()
        await set_auth_write_gate(self.session, allow_status_write=False)
        await self.audit.record(
            action="user.status",
            resource="user",
            resource_id=str(user.id),
            tenant_id=self.ctx.tenant_id,
            user_id=self.ctx.user_id,
            metadata={"status": status},
        )
        await notify_account_email(
            self.session,
            user,
            template="ACCOUNT_STATUS_CHANGED",
            ctx=self.ctx,
            context={"status": status},
        )
        return await self._public_for(user)

    async def _public_for(self, user: User) -> dict:
        role = await self.session.get(Role, user.role_id) if user.role_id else None
        branch = await self.session.get(Branch, user.branch_id) if user.branch_id else None
        return to_public(
            (
                user,
                role.name if role else None,
                role.code if role else None,
                branch.name if branch else None,
                branch.code if branch else None,
            )
        )

    async def _assert_email_available(self, email: str) -> None:
        await set_rls_bypass(self.session, True)
        existing = await self.session.scalar(
            select(User.id).where(
                func.lower(User.email) == email,
                User.deleted_at.is_(None),
            )
        )
        await set_rls_bypass(self.session, False)
        if existing is not None:
            raise ConflictError("A user with this email already exists")

    async def _require_assignable_role(self, role_id: UUID) -> Role:
        role = await self.session.get(Role, role_id)
        if (
            role is None
            or role.deleted_at is not None
            or role.status != RoleStatus.ACTIVE.value
        ):
            raise ValidationAppError("Role not found")
        if role.tenant_id is None:
            if not self.ctx.is_platform_admin:
                raise ValidationAppError("Role not found")
        elif role.tenant_id != self.ctx.tenant_id and not self.ctx.is_platform_admin:
            raise ValidationAppError("Role not found")
        if role.code == "platform_admin" and not self.ctx.is_platform_admin:
            raise AuthorizationError()
        if (
            role.code in _PROTECTED_ROLE_CODES
            and not self.ctx.is_platform_admin
            and not self.ctx.allows("role:manage")
        ):
            raise AuthorizationError()
        return role

    async def _assignable_roles(self) -> list[Role]:
        stmt = select(Role).where(
            Role.deleted_at.is_(None),
            Role.status == RoleStatus.ACTIVE.value,
        )
        if self.ctx.is_platform_admin:
            stmt = stmt.where(
                (Role.tenant_id == self.ctx.tenant_id) | (Role.tenant_id.is_(None))
            )
        else:
            stmt = stmt.where(Role.tenant_id == self.ctx.tenant_id)
            if not self.ctx.allows("role:manage"):
                stmt = stmt.where(Role.code.notin_(tuple(_PROTECTED_ROLE_CODES)))
        stmt = stmt.order_by(Role.is_system.desc(), Role.name)
        return list((await self.session.scalars(stmt)).all())

    async def _assignable_branches(self) -> list[Branch]:
        stmt = select(Branch).where(
            Branch.tenant_id == self.ctx.tenant_id,
            Branch.deleted_at.is_(None),
            Branch.status == "ACTIVE",
        )
        if (
            not self.ctx.is_platform_admin
            and self.ctx.branch_scope == BranchScope.ASSIGNED
            and self.ctx.branch_ids
        ):
            stmt = stmt.where(Branch.id.in_(self.ctx.branch_ids))
        stmt = stmt.order_by(Branch.name)
        return list((await self.session.scalars(stmt)).all())
