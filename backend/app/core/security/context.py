"""Request-scoped tenant / principal security context.

Tenant identity is NEVER taken from the client request body/query.
Role and permissions are bound from a live DB role lookup on each request
(JWT carries identity only). Session validity is re-checked every request.
"""
from dataclasses import dataclass, field
from uuid import UUID

from app.core.exceptions import AuthorizationError, TenantAccessError, TenantSuspendedError
from app.core.logging.context import set_tenant_id, set_user_id
from app.core.security.branch_scope import BranchScope
from app.core.security.permissions import PLATFORM_WILDCARD


@dataclass(slots=True)
class SecurityContext:
    user_id: UUID
    tenant_id: UUID
    session_id: UUID
    email: str
    role_id: UUID
    role_code: str
    is_platform_admin: bool = False
    tenant_status: str = "ACTIVE"
    permissions: set[str] = field(default_factory=set)
    branch_scope: BranchScope = BranchScope.NONE
    branch_ids: set[UUID] = field(default_factory=set)
    home_branch_id: UUID | None = None
    app_env: str = "development"
    # Guest quote screen — capability cookie, not a real user principal.
    is_guest: bool = False
    # Bound from the live user row at auth time — avoid a second users lookup.
    actor_display_name: str | None = None
    # Sales Agent logins only: the approved intermediary this user sells as.
    agent_intermediary_id: UUID | None = None

    @property
    def is_sales_agent(self) -> bool:
        from app.modules.roles.permissions_catalog import SALES_AGENT_ROLE_CODE

        return not self.is_platform_admin and self.role_code == SALES_AGENT_ROLE_CODE

    @property
    def actor_user_id(self) -> UUID | None:
        """FK-safe actor: guests never write a synthetic user id to the database."""
        return None if self.is_guest else self.user_id

    def bind(self) -> None:
        set_user_id(str(self.user_id) if not self.is_guest else f"guest:{self.session_id}")
        set_tenant_id(str(self.tenant_id))

    def require_active_tenant(self) -> None:
        if self.tenant_status in {"SUSPENDED", "DISABLED", "ARCHIVED"}:
            raise TenantSuspendedError()

    def require_staff_principal(self) -> None:
        """Staff services must reject a guest execution adapter."""
        if self.is_guest:
            raise AuthorizationError("This action requires an authenticated staff session")

    def require_permission(self, permission: str) -> None:
        if self.is_guest:
            raise AuthorizationError("Guest session cannot use staff permissions")
        if permission not in self.permissions and not self._has_wildcard(permission):
            raise AuthorizationError()

    def require_any_permission(self, *permissions: str) -> None:
        if self.is_guest:
            raise AuthorizationError("Guest session cannot use staff permissions")
        if not any(p in self.permissions or self._has_wildcard(p) for p in permissions):
            raise AuthorizationError()

    def assert_same_tenant(self, resource_tenant_id: UUID) -> None:
        if resource_tenant_id != self.tenant_id and not self.is_platform_admin:
            raise TenantAccessError()

    def assert_branch_access(self, resource_branch_id: UUID | None) -> None:
        from app.core.security.branch_scope import authorize_branch_access

        authorize_branch_access(self, resource_branch_id)

    def assert_owner_or_permission(
        self,
        owner_user_id: UUID | None,
        *permissions: str,
    ) -> None:
        """Allow if caller owns the row or holds an elevated permission."""
        if owner_user_id is not None and owner_user_id == self.user_id:
            return
        if permissions:
            self.require_any_permission(*permissions)
            return
        raise AuthorizationError()

    def allows(self, *permissions: str) -> bool:
        try:
            if len(permissions) == 1:
                self.require_permission(permissions[0])
            else:
                self.require_any_permission(*permissions)
            return True
        except AuthorizationError:
            return False

    def can_manage_users(self) -> bool:
        return self.is_platform_admin or bool(
            self.permissions & {"user:manage", "user:write", "role:manage"}
        )

    def _has_wildcard(self, permission: str) -> bool:
        if not self.is_platform_admin:
            return False
        return PLATFORM_WILDCARD in self.permissions or permission.startswith("platform:")
