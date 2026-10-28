"""Guest-plane capabilities — not the staff permission catalog.

A guest session is a capability token. It may hold only the values in
``GuestCapability``. Staff codes such as ``customer:create`` are never
granted to a guest and cannot authorize a guest.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import StrEnum
from uuid import UUID

from app.core.exceptions import AuthorizationError, TenantSuspendedError
from app.core.logging.context import set_tenant_id, set_user_id
from app.core.security.branch_scope import BranchScope


class GuestCapability(StrEnum):
    CREATE_QUOTE = "create_guest_quote"
    VIEW_QUOTE = "view_guest_quote"
    INITIATE_PAYMENT = "initiate_guest_payment"
    VIEW_PAYMENT = "view_guest_payment_status"
    DOWNLOAD_CERTIFICATE = "download_own_guest_certificate"
    FILE_CLAIM = "file_guest_claim"
    VIEW_OWN_CLAIM = "view_own_guest_claim"
    FOLLOW_UP_CLAIM = "follow_up_guest_claim"
    APPLY_AS_AGENT = "apply_as_guest_agent"


# Every valid guest session receives this closed set. Adding a staff
# permission code here is a defect — use a new GuestCapability instead.
GUEST_CAPABILITIES: frozenset[GuestCapability] = frozenset(GuestCapability)


@dataclass(slots=True)
class GuestContext:
    """Principal for the guest quote plane. Not a staff SecurityContext."""

    session_id: UUID
    tenant_id: UUID
    tenant_status: str
    app_env: str
    capabilities: frozenset[GuestCapability] = field(default_factory=lambda: GUEST_CAPABILITIES)
    jti: str = ""

    def bind(self) -> None:
        set_user_id(f"guest:{self.session_id}")
        set_tenant_id(str(self.tenant_id))

    def require(self, *needed: GuestCapability) -> None:
        if not needed or not all(item in self.capabilities for item in needed):
            raise AuthorizationError("Guest session cannot perform this action")

    def require_active_tenant(self) -> None:
        if self.tenant_status in {"SUSPENDED", "DISABLED", "ARCHIVED"}:
            raise TenantSuspendedError()

    def as_execution_context(self):
        """Narrow adapter for existing tenant-scoped repositories.

        Permissions stay empty. ``is_guest`` is True so staff
        ``require_permission`` / ``require_staff_principal`` fail closed.
        """
        from app.core.security.context import SecurityContext

        ctx = SecurityContext(
            user_id=self.session_id,
            tenant_id=self.tenant_id,
            session_id=self.session_id,
            email="guest@starserve.local",
            role_id=UUID(int=0),
            role_code="guest",
            is_platform_admin=False,
            tenant_status=self.tenant_status,
            permissions=set(),
            branch_scope=BranchScope.ALL_TENANT,
            branch_ids=set(),
            app_env=self.app_env,
            is_guest=True,
        )
        ctx.bind()
        return ctx
