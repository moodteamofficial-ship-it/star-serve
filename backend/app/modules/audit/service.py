"""Audit service — never log secrets."""

from typing import Any
from uuid import UUID

from sqlalchemy.ext.asyncio import AsyncSession

from app.core.logging.context import get_correlation_id, get_job_id, get_request_id
from app.modules.audit.models import AuditEvent

_SENSITIVE_KEYS = {
    "password",
    "token",
    "refresh_token",
    "access_token",
    "authorization",
    "secret",
    "api_key",
    "basic_auth",
    "pin",
}


def _scrub(metadata: dict[str, Any] | None) -> dict[str, Any]:
    if not metadata:
        return {}
    cleaned: dict[str, Any] = {}
    for key, value in metadata.items():
        if key.lower() in _SENSITIVE_KEYS or any(s in key.lower() for s in _SENSITIVE_KEYS):
            cleaned[key] = "[REDACTED]"
        else:
            cleaned[key] = value
    return cleaned


class AuditService:
    def __init__(self, session: AsyncSession) -> None:
        self.session = session

    async def record(
        self,
        *,
        action: str,
        resource: str,
        resource_id: str | None = None,
        tenant_id: UUID | None = None,
        user_id: UUID | None = None,
        result: str = "SUCCESS",
        ip_address: str | None = None,
        user_agent: str | None = None,
        message: str | None = None,
        metadata: dict[str, Any] | None = None,
        flush: bool = True,
    ) -> AuditEvent:
        event = AuditEvent(
            tenant_id=tenant_id,
            user_id=user_id,
            action=action,
            resource=resource,
            resource_id=resource_id,
            result=result,
            ip_address=ip_address,
            user_agent=user_agent,
            request_id=get_request_id(),
            job_id=get_job_id(),
            correlation_id=get_correlation_id(),
            metadata_json=_scrub(metadata),
            message=message,
        )
        self.session.add(event)
        if flush:
            await self.session.flush()
        return event
