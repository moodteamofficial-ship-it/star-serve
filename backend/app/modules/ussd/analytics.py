"""USSD analytics aggregations from structured session events."""

from __future__ import annotations

from datetime import UTC, datetime, timedelta
from typing import Any
from uuid import UUID

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.modules.ussd.enums import UssdEventType, UssdSessionStatus
from app.modules.ussd.models import UssdSession, UssdSessionEvent

# Metric definitions (denominators use session start time unless noted):
# session_completion_rate = completed workflow sessions / eligible ended sessions * 100
# step_abandonment_rate = drop-off to the next funnel step / sessions that reached this step
# validation_failure_rate = VALIDATION_FAILED events / INPUT_RECEIVED+OPTION_SELECTED+VALIDATION_FAILED
# unique_access_count = distinct msisdn_hash (pseudonymized), not people

_FUNNEL_STEP_ORDER = {
    "MOTOR_QUOTE": (
        "category",
        "product",
        "cover_option",
        "cover_period",
        "make",
        "model",
        "id_number",
        "full_name",
        "email",
        "vehicle_registration",
        "chassis",
        "confirm",
        "_workflow",
    ),
    "REPORT_CLAIM": (
        "policy_number",
        "vehicle_registration",
        "id_number",
        "phone",
        "incident_date",
        "incident_location",
        "incident_description",
        "confirm",
        "_workflow",
    ),
    "FOLLOW_UP_CLAIM": (
        "claim_number",
        "id_number",
        "_workflow",
    ),
}


async def overview_metrics(
    session: AsyncSession,
    *,
    tenant_id: UUID,
    start: datetime,
    end: datetime,
    include_test: bool = False,
) -> dict[str, Any]:
    sess_filters = [
        UssdSession.tenant_id == tenant_id,
        UssdSession.created_at >= start,
        UssdSession.created_at < end,
    ]
    if not include_test:
        sess_filters.append(UssdSession.is_test.is_(False))

    total_sessions = await session.scalar(
        select(func.count()).select_from(UssdSession).where(*sess_filters)
    ) or 0
    unique_access = await session.scalar(
        select(func.count(func.distinct(UssdSession.msisdn_hash))).where(*sess_filters)
    ) or 0
    completed = await session.scalar(
        select(func.count()).select_from(UssdSession).where(
            *sess_filters, UssdSession.status == UssdSessionStatus.COMPLETED.value
        )
    ) or 0
    # Incomplete outcomes — include FAILED (common for cancelled/rejected dials).
    abandoned = await session.scalar(
        select(func.count()).select_from(UssdSession).where(
            *sess_filters,
            UssdSession.status.in_(
                [
                    UssdSessionStatus.ABANDONED.value,
                    UssdSessionStatus.TIMED_OUT.value,
                    UssdSessionStatus.TERMINATED.value,
                    UssdSessionStatus.FAILED.value,
                ]
            ),
        )
    ) or 0
    active = await session.scalar(
        select(func.count()).select_from(UssdSession).where(
            *sess_filters, UssdSession.status == UssdSessionStatus.ACTIVE.value
        )
    ) or 0

    event_filters = [
        UssdSessionEvent.tenant_id == tenant_id,
        UssdSessionEvent.created_at >= start,
        UssdSessionEvent.created_at < end,
    ]
    if not include_test:
        event_filters.append(UssdSessionEvent.is_test.is_(False))

    total_requests = await session.scalar(
        select(func.count()).select_from(UssdSessionEvent).where(
            *event_filters,
            UssdSessionEvent.event_type.in_(
                [
                    UssdEventType.SESSION_STARTED.value,
                    UssdEventType.SESSION_RESUMED.value,
                    UssdEventType.REQUEST_RECEIVED.value,
                ]
            ),
        )
    ) or 0
    validation_failures = await session.scalar(
        select(func.count()).select_from(UssdSessionEvent).where(
            *event_filters,
            UssdSessionEvent.event_type == UssdEventType.VALIDATION_FAILED.value,
        )
    ) or 0
    technical_errors = await session.scalar(
        select(func.count()).select_from(UssdSessionEvent).where(
            *event_filters,
            UssdSessionEvent.event_type == UssdEventType.TECHNICAL_ERROR.value,
        )
    ) or 0
    duplicates = await session.scalar(
        select(func.count()).select_from(UssdSessionEvent).where(
            *event_filters,
            UssdSessionEvent.event_type == UssdEventType.DUPLICATE_CALLBACK.value,
        )
    ) or 0

    ended = completed + abandoned
    completion_rate = round((completed / ended) * 100, 1) if ended else 0.0
    abandonment_rate = round((abandoned / ended) * 100, 1) if ended else 0.0

    by_workflow = await session.execute(
        select(
            UssdSession.workflow_action,
            func.count(),
        )
        .where(*sess_filters, UssdSession.workflow_action.is_not(None))
        .group_by(UssdSession.workflow_action)
    )

    return {
        "period": {"start": start.isoformat(), "end": end.isoformat()},
        "total_requests": int(total_requests),
        "total_sessions": int(total_sessions),
        "unique_access_count": int(unique_access),
        "unique_access_definition": (
            "Distinct pseudonymized MSISDN hashes (msisdn_hash). "
            "Not a count of verified people."
        ),
        "active_sessions": int(active),
        "completed_sessions": int(completed),
        "abandoned_or_timed_out": int(abandoned),
        "session_completion_rate": completion_rate,
        "session_abandonment_rate": abandonment_rate,
        "validation_failures": int(validation_failures),
        "technical_errors": int(technical_errors),
        "duplicate_callbacks": int(duplicates),
        "sessions_by_workflow": {
            (row[0] or "NONE"): int(row[1]) for row in by_workflow.all()
        },
        "metric_definitions": {
            "session_completion_rate": (
                "Successfully completed sessions / (completed + abandoned/timed_out/terminated) * 100. "
                "Period based on session created_at."
            ),
            "session_abandonment_rate": (
                "Abandoned, timed out, terminated, or failed sessions / eligible ended sessions * 100."
            ),
            "unique_access_count": (
                "Count of distinct msisdn_hash values in the period."
            ),
        },
    }


async def funnel_metrics(
    session: AsyncSession,
    *,
    tenant_id: UUID,
    workflow: str,
    start: datetime,
    end: datetime,
    include_test: bool = False,
) -> dict[str, Any]:
    filters = [
        UssdSessionEvent.tenant_id == tenant_id,
        UssdSessionEvent.workflow_action == workflow,
        UssdSessionEvent.created_at >= start,
        UssdSessionEvent.created_at < end,
    ]
    if not include_test:
        filters.append(UssdSessionEvent.is_test.is_(False))

    rows = await session.execute(
        select(
            UssdSessionEvent.step_id,
            UssdSessionEvent.event_type,
            func.count(func.distinct(UssdSessionEvent.session_id)),
        )
        .where(*filters)
        .group_by(UssdSessionEvent.step_id, UssdSessionEvent.event_type)
    )
    reached_rows = await session.execute(
        select(
            UssdSessionEvent.step_id,
            func.count(func.distinct(UssdSessionEvent.session_id)),
        )
        .where(*filters)
        .group_by(UssdSessionEvent.step_id)
    )
    reached_by_step = {
        (step_id or "_workflow"): int(count) for step_id, count in reached_rows.all()
    }
    stages: dict[str, dict[str, int]] = {}
    workflow_entered = 0
    workflow_succeeded = 0
    for step_id, event_type, count in rows.all():
        c = int(count)
        if event_type == UssdEventType.WORKFLOW_ENTERED.value:
            workflow_entered += c
        if event_type == UssdEventType.WORKFLOW_SUCCEEDED.value:
            workflow_succeeded += c
        key = step_id or "_workflow"
        bucket = stages.setdefault(
            key,
            {
                "entered": 0,
                "completed": 0,
                "validation_failed": 0,
                "technical_errors": 0,
                "nav_back": 0,
                "succeeded": 0,
            },
        )
        if event_type == UssdEventType.STEP_COMPLETED.value:
            bucket["completed"] += c
        elif event_type == UssdEventType.VALIDATION_FAILED.value:
            bucket["validation_failed"] += c
        elif event_type == UssdEventType.TECHNICAL_ERROR.value:
            bucket["technical_errors"] += c
        elif event_type == UssdEventType.NAV_BACK.value:
            bucket["nav_back"] += c
        elif event_type == UssdEventType.WORKFLOW_SUCCEEDED.value:
            bucket["succeeded"] += c

    for key, reached in reached_by_step.items():
        bucket = stages.setdefault(
            key,
            {
                "entered": 0,
                "completed": 0,
                "validation_failed": 0,
                "technical_errors": 0,
                "nav_back": 0,
                "succeeded": 0,
            },
        )
        bucket["entered"] = reached

    order = _FUNNEL_STEP_ORDER.get(workflow) or ()
    rank = {name: idx for idx, name in enumerate(order)}

    def _step_sort_key(item: tuple[str, dict[str, int]]) -> tuple[int, str]:
        step = item[0] or ""
        return (rank.get(step, 10_000), step)

    ordered = sorted(stages.items(), key=_step_sort_key)
    table = []
    for index, (step, stats) in enumerate(ordered):
        entered = int(stats["entered"] or 0)
        # Drop-off vs the next funnel step (or vs success on the last rung).
        if index + 1 < len(ordered):
            next_entered = int(ordered[index + 1][1]["entered"] or 0)
            abandoned_at = max(entered - next_entered, 0)
        else:
            abandoned_at = max(entered - int(stats["succeeded"] or workflow_succeeded), 0)
        rate = round((abandoned_at / entered) * 100, 1) if entered else 0.0
        table.append(
            {
                "step_id": step,
                **stats,
                "entered": entered,
                "abandoned_at_step": abandoned_at,
                "step_abandonment_rate": rate,
            }
        )
    insight = None
    if table:
        worst = max(table, key=lambda r: r["step_abandonment_rate"])
        if worst["step_abandonment_rate"] > 0 and worst["entered"] >= 3:
            insight = (
                f"Most sessions that stall in {workflow} leave during "
                f"{worst['step_id']} ({worst['step_abandonment_rate']}% abandonment)."
            )

    # Card metrics for the selected workflow — same source as the funnel table.
    started = workflow_entered or (table[0]["entered"] if table else 0)
    succeeded = workflow_succeeded
    incomplete = max(started - succeeded, 0)
    completion_rate = round((succeeded / started) * 100, 1) if started else 0.0
    abandonment_rate = round((incomplete / started) * 100, 1) if started else 0.0

    return {
        "workflow": workflow,
        "period": {"start": start.isoformat(), "end": end.isoformat()},
        "stages": table,
        "insight": insight,
        "summary": {
            "sessions": int(started),
            "completed": int(succeeded),
            "abandoned": int(incomplete),
            "session_completion_rate": completion_rate,
            "session_abandonment_rate": abandonment_rate,
        },
    }


def parse_period(preset: str | None, start: str | None, end: str | None) -> tuple[datetime, datetime]:
    now = datetime.now(UTC)
    end_dt = now
    if preset == "today":
        start_dt = datetime(now.year, now.month, now.day, tzinfo=UTC)
    elif preset == "yesterday":
        day = datetime(now.year, now.month, now.day, tzinfo=UTC) - timedelta(days=1)
        start_dt = day
        end_dt = day + timedelta(days=1)
    elif preset == "last_7_days":
        start_dt = now - timedelta(days=7)
    elif preset == "last_30_days":
        start_dt = now - timedelta(days=30)
    else:
        start_dt = now - timedelta(days=7)
    if start:
        start_dt = datetime.fromisoformat(start.replace("Z", "+00:00"))
    if end:
        end_dt = datetime.fromisoformat(end.replace("Z", "+00:00"))
    return start_dt, end_dt
