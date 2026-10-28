"""Durable, idempotent USSD analytics events."""

from __future__ import annotations

import hashlib
from typing import Any
from uuid import UUID, uuid4

from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.ext.asyncio import AsyncSession

from app.modules.ussd.models import UssdSessionEvent

_EVENT_KEY_MAX = 128


def fit_event_key(key: str, *, max_len: int = _EVENT_KEY_MAX) -> str:
    """Keep event keys within the DB column while preserving uniqueness."""
    if len(key) <= max_len:
        return key
    digest = hashlib.sha256(key.encode("utf-8")).hexdigest()[:16]
    keep = max(8, max_len - len(digest) - 1)
    return f"{key[:keep]}:{digest}"


async def record_event(
    session: AsyncSession,
    *,
    tenant_id: UUID,
    session_id: UUID,
    event_type: str,
    event_key: str | None = None,
    workflow_action: str | None = None,
    step_id: str | None = None,
    screen_key: str | None = None,
    config_version: int | None = None,
    outcome: str | None = None,
    error_category: str | None = None,
    duration_ms: int | None = None,
    provider_kind: str | None = None,
    correlation_id: str | None = None,
    msisdn_hash: str | None = None,
    is_test: bool = False,
    metadata: dict[str, Any] | None = None,
) -> None:
    key = fit_event_key(event_key or f"{event_type}:{uuid4().hex[:12]}")
    stmt = (
        insert(UssdSessionEvent)
        .values(
            id=uuid4(),
            tenant_id=tenant_id,
            session_id=session_id,
            event_key=key,
            event_type=event_type,
            workflow_action=workflow_action,
            step_id=step_id,
            screen_key=screen_key,
            config_version=config_version,
            outcome=outcome,
            error_category=error_category,
            duration_ms=duration_ms,
            provider_kind=provider_kind,
            correlation_id=correlation_id,
            msisdn_hash=msisdn_hash,
            is_test=is_test,
            metadata_json=metadata or {},
        )
        .on_conflict_do_nothing(constraint="uq_ussd_session_events_key")
    )
    await session.execute(stmt)
