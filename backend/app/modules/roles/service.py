"""Permission / role loading and evaluation — always from the database."""

from dataclasses import dataclass
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database.rls import set_rls_bypass
from app.core.exceptions import AuthenticationError, AuthorizationError
from app.modules.roles.models import Permission, Role, RolePermission, UserRole
from app.modules.roles.permissions_catalog import PERMISSION_CATALOG
from app.modules.users.models import User


@dataclass(frozen=True, slots=True)
class ResolvedRole:
    role_id: UUID
    code: str
    name: str
    tenant_id: UUID | None
    permissions: frozenset[str]


async def ensure_catalog_permissions(session: AsyncSession) -> bool:
    """Insert catalog permissions missing from the live roles board.

    Configuration → Roles reads this table. New codes such as ``user:update``
    must exist here so they can be enabled or disabled per role.
    """
    existing = {p.code: p for p in (await session.scalars(select(Permission))).all()}
    added = False
    await set_rls_bypass(session, True)
    try:
        for item in PERMISSION_CATALOG:
            row = existing.get(item["code"])
            if row is None:
                session.add(
                    Permission(
                        code=item["code"],
                        description=item.get("description"),
                        category=item.get("category"),
                    )
                )
                added = True
                continue
            if not row.description and item.get("description"):
                row.description = item["description"]
                added = True
            if not row.category and item.get("category"):
                row.category = item["category"]
                added = True
        if added:
            await session.flush()
    finally:
        await set_rls_bypass(session, False)
    return added


async def load_permissions_for_role(session: AsyncSession, *, role_id: UUID) -> set[str]:
    stmt = (
        select(Permission.code)
        .join(RolePermission, RolePermission.permission_id == Permission.id)
        .where(RolePermission.role_id == role_id)
    )
    result = await session.scalars(stmt)
    return set(result.all())


async def load_user_permissions(session: AsyncSession, *, user_id: UUID) -> set[str]:
    """Legacy union of all assigned roles — prefer resolve_user_role for auth."""
    stmt = (
        select(Permission.code)
        .join(RolePermission, RolePermission.permission_id == Permission.id)
        .join(Role, Role.id == RolePermission.role_id)
        .join(UserRole, UserRole.role_id == Role.id)
        .where(UserRole.user_id == user_id)
    )
    result = await session.scalars(stmt)
    return set(result.all())


async def load_user_branch_ids(session: AsyncSession, *, user_id: UUID) -> set[UUID]:
    from app.modules.users.models import User, UserBranch

    result = await session.scalars(select(UserBranch.branch_id).where(UserBranch.user_id == user_id))
    ids = set(result.all())
    home = await session.scalar(select(User.branch_id).where(User.id == user_id))
    if home is not None:
        ids.add(home)
    return ids


async def user_has_role_assignment(
    session: AsyncSession, *, user_id: UUID, role_id: UUID
) -> bool:
    stmt = select(UserRole.id).where(
        UserRole.user_id == user_id,
        UserRole.role_id == role_id,
        UserRole.deleted_at.is_(None),
        UserRole.status == "ACTIVE",
    )
    return await session.scalar(stmt) is not None


async def resolve_user_role(session: AsyncSession, *, user: User) -> ResolvedRole:
    """Validate users.role_id exists, is assigned, and load that role's permissions only.

    Sign-in and every authenticated request must go through this path so access
    cannot drift from the roles table.
    """
    if user.deleted_at is not None or user.status == "DELETED":
        raise AuthenticationError("Account has been deleted")

    if user.role_id is None:
        raise AuthenticationError("Account has no role assigned")

    # Role + assignment + permissions in one round-trip
    stmt = (
        select(Role, Permission.code)
        .join(
            UserRole,
            (UserRole.role_id == Role.id)
            & (UserRole.user_id == user.id)
            & (UserRole.deleted_at.is_(None))
            & (UserRole.status == "ACTIVE"),
        )
        .outerjoin(RolePermission, RolePermission.role_id == Role.id)
        .outerjoin(Permission, Permission.id == RolePermission.permission_id)
        .where(Role.id == user.role_id)
    )
    rows = (await session.execute(stmt)).all()
    if not rows:
        # Distinguish missing role vs missing assignment
        role = await session.get(Role, user.role_id)
        if role is None or role.deleted_at is not None or role.status == "DELETED":
            raise AuthenticationError("Assigned role no longer exists")
        if role.status != "ACTIVE":
            raise AuthenticationError("Assigned role is disabled")
        raise AuthenticationError("Role is not assigned to this user")

    role = rows[0][0]
    if role.tenant_id is not None and role.tenant_id != user.tenant_id:
        raise AuthenticationError("Role does not belong to this organization")
    if role.status != "ACTIVE" or role.deleted_at is not None:
        raise AuthenticationError("Assigned role is disabled")

    permissions = {code for _, code in rows if code}
    if not permissions and not user.is_platform_admin:
        raise AuthorizationError("Role has no permissions configured")

    return ResolvedRole(
        role_id=role.id,
        code=role.code,
        name=role.name,
        tenant_id=role.tenant_id,
        permissions=frozenset(permissions),
    )


async def assert_session_role_matches(
    *,
    user: User,
    session_role_id: UUID | None,
    resolved: ResolvedRole,
) -> None:
    """Reject sessions whose role snapshot no longer matches the live primary role."""
    if session_role_id is None:
        raise AuthenticationError("Session is missing role binding")
    if session_role_id != user.role_id or session_role_id != resolved.role_id:
        raise AuthenticationError("Session role is no longer valid — please sign in again")
