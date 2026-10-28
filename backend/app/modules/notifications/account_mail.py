"""Best-effort account emails — never fail the action that triggered them."""

from __future__ import annotations

from datetime import UTC, datetime
from typing import Any
from uuid import UUID
from zoneinfo import ZoneInfo

from sqlalchemy.ext.asyncio import AsyncSession

from app.core.exceptions import (
    AuthorizationError,
    ResourceNotFoundError,
    ServiceDisabledError,
    TenantAccessError,
    ValidationAppError,
)
from app.core.logging import get_logger
from app.core.security.branch_scope import BranchScope
from app.core.security.context import SecurityContext
from app.modules.notifications.enums import NotificationChannel
from app.modules.notifications.service import NotificationService
from app.modules.users.models import User

logger = get_logger(__name__)
_NAIROBI = ZoneInfo("Africa/Nairobi")


def device_label(user_agent: str | None) -> str:
    raw = (user_agent or "").strip()
    if not raw:
        return "Unknown device"
    lowered = raw.lower()
    if "iphone" in lowered or "android" in lowered or "mobile" in lowered:
        kind = "phone"
    elif "ipad" in lowered or "tablet" in lowered:
        kind = "tablet"
    else:
        kind = "computer"
    if "edg/" in lowered:
        browser = "Edge"
    elif "chrome/" in lowered and "chromium" not in lowered:
        browser = "Chrome"
    elif "firefox/" in lowered:
        browser = "Firefox"
    elif "safari/" in lowered and "chrome" not in lowered:
        browser = "Safari"
    else:
        browser = "Browser"
    return f"{browser} on {kind}"


def sign_in_stamp(when: datetime | None = None) -> str:
    moment = when or datetime.now(UTC)
    if moment.tzinfo is None:
        moment = moment.replace(tzinfo=UTC)
    return moment.astimezone(_NAIROBI).strftime("%d %b %Y, %H:%M EAT")


def context_for_account(user: User, *, session_id: UUID, tenant_status: str) -> SecurityContext:
    return SecurityContext(
        user_id=user.id,
        tenant_id=user.tenant_id,
        session_id=session_id,
        email=user.email,
        role_id=user.role_id or user.id,
        role_code="",
        is_platform_admin=bool(user.is_platform_admin),
        tenant_status=tenant_status or "ACTIVE",
        permissions=set(),
        branch_scope=BranchScope.ALL_TENANT,
        home_branch_id=user.branch_id,
        actor_display_name=user.full_name,
        app_env=getattr(user, "preferred_app_env", None) or "development",
    )


async def notify_account_email(
    session: AsyncSession,
    user: User,
    *,
    template: str,
    context: dict[str, Any] | None = None,
    ctx: SecurityContext | None = None,
    session_id: UUID | None = None,
    tenant_status: str = "ACTIVE",
) -> None:
    recipient = (user.email or "").strip()
    if not recipient or "@" not in recipient:
        return
    actor = ctx or context_for_account(
        user,
        session_id=session_id or user.id,
        tenant_status=tenant_status,
    )
    payload = {"recipient_name": user.full_name or "", **(context or {})}
    try:
        await NotificationService(session, actor).enqueue_transactional(
            channel=NotificationChannel.EMAIL.value,
            template_code=template,
            recipient=recipient,
            context=payload,
            related_resource="user",
            related_resource_id=user.id,
            branch_id=user.branch_id,
        )
    except (
        ServiceDisabledError,
        ValidationAppError,
        ResourceNotFoundError,
        TenantAccessError,
        AuthorizationError,
    ):
        return
    except Exception:
        logger.warning(
            "account_email_deferred",
            extra={"template": template, "user_id": str(user.id)},
        )
