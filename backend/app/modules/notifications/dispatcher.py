"""Background email + SMS drain — never SMTP or the SMS API on a request.

Claim a batch with SKIP LOCKED, release the DB row, then talk to Gmail/SES
off the connection. Several API processes can run this loop; Postgres is the
queue. For 200k+ prefer a dedicated process:

    python -m app.modules.notifications.worker
"""

from __future__ import annotations

import asyncio
from datetime import UTC, datetime, timedelta
from typing import Any
from uuid import UUID

from sqlalchemy import bindparam, text, update
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import Settings, get_settings
from app.core.database import get_session_factory, set_rls_bypass
from app.core.logging import get_logger
from app.integrations.notifications.factory import get_notification_provider
from app.modules.notifications.enums import NotificationStatus
from app.modules.notifications.models import Notification
from app.modules.notifications.pdf_mail import attachments_metadata
# Notification.branch_id FKs branches — mapper flush fails if this table is missing.
from app.modules.tenants.models import Branch as _Branch  # noqa: F401
from app.modules.notifications.templates import (
    is_otp_template,
    redact_otp_from_body,
    redact_sensitive_context,
)
from app.modules.system_config.service import SystemConfigService

logger = get_logger(__name__)

_CLAIM = text(
    """
    WITH due AS (
      SELECT id
      FROM notifications
      WHERE status = 'QUEUED'
        AND channel IN :channels
        AND (next_retry_at IS NULL OR next_retry_at <= now())
      ORDER BY priority ASC, created_at ASC
      FOR UPDATE SKIP LOCKED
      LIMIT :batch
    )
    UPDATE notifications AS n
    SET status = 'SENDING',
        attempt_count = n.attempt_count + 1,
        updated_at = now()
    FROM due
    WHERE n.id = due.id
    RETURNING n.id
    """
).bindparams(bindparam("channels", expanding=True))

_RECOVER = text(
    """
    UPDATE notifications
    SET status = 'QUEUED',
        updated_at = now()
    WHERE status = 'SENDING'
      AND channel IN :channels
      AND updated_at < now() - (CAST(:stale AS int) * INTERVAL '1 second')
    """
).bindparams(bindparam("channels", expanding=True))

_RETRY_BACKOFF = (30, 120, 600)
_STALE_SENDING_SECONDS = 120


class EmailDispatcher:
    def __init__(self, settings: Settings | None = None) -> None:
        self.settings = settings or get_settings()
        self._stop = asyncio.Event()
        self._wakeup = asyncio.Event()
        self._task: asyncio.Task[None] | None = None
        self._sem = asyncio.Semaphore(self.settings.email_inflight)

    def wakeup(self) -> None:
        self._wakeup.set()

    def start(self) -> None:
        if self._task is not None and not self._task.done():
            return
        self._stop.clear()
        self._task = asyncio.create_task(self._supervise(), name="email-dispatcher")

    async def stop(self) -> None:
        self._stop.set()
        self._wakeup.set()
        task = self._task
        self._task = None
        if task is None:
            return
        try:
            await asyncio.wait_for(task, timeout=3.0)
        except TimeoutError:
            task.cancel()
            try:
                await task
            except asyncio.CancelledError:
                logger.warning("email_dispatcher_stop_timed_out")

    async def _supervise(self) -> None:
        while not self._stop.is_set():
            try:
                await self._run()
                return
            except Exception:
                logger.exception("email_dispatcher_crashed")
                if self._stop.is_set():
                    return
                await asyncio.sleep(1.0)

    async def _run(self) -> None:
        poll = max(float(self.settings.email_worker_poll_seconds), 0.2)
        logger.info(
            "email_dispatcher_started",
            extra={
                "provider": self.settings.resolved_email_provider,
                "rate": self.settings.email_rate_limit_per_second,
                "inflight": self.settings.email_inflight,
            },
        )
        while not self._stop.is_set():
            try:
                claimed = await asyncio.wait_for(self._drain(), timeout=60.0)
            except TimeoutError:
                logger.error("email_dispatcher_drain_timeout")
                claimed = 0
            except Exception:
                logger.exception("email_dispatcher_cycle_failed")
                claimed = 0
            if claimed:
                continue
            self._wakeup.clear()
            try:
                await asyncio.wait_for(self._wakeup.wait(), timeout=poll)
            except TimeoutError:
                continue
        logger.info("email_dispatcher_stopped")

    async def _drain(self) -> int:
        factory = get_session_factory()
        handled = list(self.settings.dispatcher_channels)
        if not handled:
            return 0
        async with factory() as session:
            await set_rls_bypass(session, True)
            await session.execute(
                _RECOVER, {"stale": _STALE_SENDING_SECONDS, "channels": handled}
            )
            config = SystemConfigService(session)
            channels = [c for c in handled if await config.outbound_allowed(c, live=True)]
            if not channels:
                await session.commit()
                return 0
            rows = await session.execute(
                _CLAIM,
                {
                    "batch": max(int(self.settings.email_worker_batch_size), 1),
                    "channels": channels,
                },
            )
            ids = [row[0] for row in rows]
            await session.commit()
        if not ids:
            return 0
        await asyncio.gather(*(self._send_one(nid) for nid in ids))
        return len(ids)

    async def _send_one(self, notification_id: UUID) -> None:
        async with self._sem:
            factory = get_session_factory()
            result: Any = None
            try:
                async with factory() as session:
                    await set_rls_bypass(session, True)
                    row = await session.get(Notification, notification_id)
                    if row is None:
                        await session.commit()
                        return
                    if not await SystemConfigService(session).outbound_allowed(
                        row.channel, live=True
                    ):
                        row.status = NotificationStatus.QUEUED.value
                        row.attempt_count = max(0, int(row.attempt_count) - 1)
                        row.last_error_code = "CHANNEL_DISABLED"
                        row.last_error_message = (
                            f"{row.channel} is switched off in system settings"
                        )
                        await session.commit()
                        return
                    result = await _transmit(row)
                    _apply_result(row, result)
                    await session.commit()
            except Exception:
                logger.exception(
                    "email_dispatch_one_failed",
                    extra={"notification_id": str(notification_id)},
                )
                if result is not None and getattr(result, "success", False):
                    await _persist_sent(notification_id, result)


_DISPATCHER: EmailDispatcher | None = None


def get_email_dispatcher() -> EmailDispatcher | None:
    return _DISPATCHER


def wakeup_email_dispatcher() -> None:
    dispatcher = _DISPATCHER
    if dispatcher is not None:
        if dispatcher._task is None or dispatcher._task.done():
            dispatcher.start()
        dispatcher.wakeup()
        return
    try:
        loop = asyncio.get_running_loop()
    except RuntimeError:
        return
    loop.create_task(_ensure_dispatcher())


async def _ensure_dispatcher() -> None:
    dispatcher = await start_email_dispatcher()
    if dispatcher is not None:
        dispatcher.wakeup()


async def start_email_dispatcher(settings: Settings | None = None) -> EmailDispatcher | None:
    global _DISPATCHER
    cfg = settings or get_settings()
    if not cfg.dispatcher_channels:
        return None
    if _DISPATCHER is None:
        _DISPATCHER = EmailDispatcher(cfg)
    _DISPATCHER.start()
    return _DISPATCHER


async def stop_email_dispatcher() -> None:
    global _DISPATCHER
    dispatcher = _DISPATCHER
    _DISPATCHER = None
    if dispatcher is not None:
        await dispatcher.stop()


async def _transmit(row: Notification) -> Any:
    provider = get_notification_provider(row.channel)
    return await provider.send(
        recipient=row.recipient,
        subject=row.subject,
        body=row.body,
        metadata={
            "template": row.template_code,
            "notification_id": str(row.id),
            "tenant_id": str(row.tenant_id),
            "context": dict(row.context_json or {}),
            "attachments": attachments_metadata(row),
        },
    )


def _apply_result(row: Notification, result: Any) -> None:
    row.provider = result.provider_name
    row.provider_payload = result.raw
    if result.success:
        row.status = NotificationStatus.SENT.value
        row.provider_message_id = result.provider_message_id
        row.sent_at = datetime.now(UTC)
        row.last_error_code = None
        row.last_error_message = None
        row.next_retry_at = None
        if is_otp_template(row.template_code):
            row.body = redact_otp_from_body(row.body, row.context_json)
            row.context_json = redact_sensitive_context(row.context_json)
        return
    row.last_error_code = result.error_code
    row.last_error_message = result.error_message
    permanent = result.error_code in {
        "AUTH_FAILED",
        "REJECTED",
        "INVALID_RECIPIENT",
        "NOT_CONFIGURED",
    }
    if permanent or row.attempt_count >= row.max_attempts:
        row.status = NotificationStatus.FAILED.value
        row.next_retry_at = None
        return
    row.status = NotificationStatus.QUEUED.value
    backoff = _RETRY_BACKOFF[min(row.attempt_count - 1, len(_RETRY_BACKOFF) - 1)]
    row.next_retry_at = datetime.now(UTC) + timedelta(seconds=backoff)


async def _persist_sent(notification_id: UUID, result: Any) -> None:
    """Record a successful SMTP send when the ORM commit cannot flush."""
    factory = get_session_factory()
    try:
        async with factory() as session:
            await set_rls_bypass(session, True)
            await session.execute(
                update(Notification)
                .where(Notification.id == notification_id)
                .values(
                    status=NotificationStatus.SENT.value,
                    provider=result.provider_name,
                    provider_message_id=result.provider_message_id,
                    provider_payload=result.raw or {},
                    last_error_code=None,
                    last_error_message=None,
                    next_retry_at=None,
                    sent_at=datetime.now(UTC),
                )
            )
            await session.commit()
    except Exception:
        logger.exception(
            "email_dispatch_persist_sent_failed",
            extra={"notification_id": str(notification_id)},
        )


async def mark_due_queued(session: AsyncSession, notification_id: UUID) -> None:
    await session.execute(
        update(Notification)
        .where(Notification.id == notification_id)
        .values(status=NotificationStatus.QUEUED.value)
    )
