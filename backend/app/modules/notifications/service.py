"""Notification service — queue + deliver via provider ports."""

from __future__ import annotations

from datetime import UTC, datetime, timedelta
from typing import Any
from uuid import UUID

from sqlalchemy import func, or_, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import get_settings
from app.core.database.enums import JobStatus, JobType
from app.core.exceptions import ValidationAppError
from app.core.idempotency.service import IdempotencyService
from app.core.security.context import SecurityContext
from app.core.security.media_url import sanitize_avatar_url
from app.integrations.notifications.factory import get_notification_provider
from app.modules.audit.service import AuditService
from app.modules.customers.models import Customer
from app.modules.jobs.models import IdempotencyKey
from app.modules.jobs.service import JobService
from app.modules.notifications.dispatcher import wakeup_email_dispatcher
from app.modules.notifications.enums import NotificationChannel, NotificationStatus
from app.modules.notifications.models import Notification
from app.modules.notifications.pdf_mail import attachments_metadata
from app.modules.notifications.repository import NotificationRepository
from app.modules.notifications.schemas import NotificationSendRequest
from app.modules.notifications.templates import (
    is_known_template,
    is_otp_template,
    is_staff_template,
    list_template_codes,
    redact_otp_from_body,
    redact_sensitive_context,
    render_template,
    sanitize_template_context,
    template_priority,
)
from app.modules.users.models import User

_STAFF_SEND_CAP_PER_HOUR = 20

# Exponential backoff seconds per attempt index (1-based after first failure)
_RETRY_BACKOFF = (30, 120, 600)


def _safe_avatar_url(value: str | None) -> str | None:
    if not value:
        return None
    try:
        return sanitize_avatar_url(value, allowed_hosts=get_settings().avatar_url_hosts)
    except ValidationAppError:
        return None


def _customer_display_name(customer: Customer) -> str | None:
    name = " ".join(part for part in (customer.first_name, customer.last_name) if part).strip()
    return name or None


def to_public(row: Notification) -> dict[str, Any]:
    context = dict(row.context_json or {})
    recipient_name = str(context.get("recipient_name") or "").strip() or None
    return {
        "id": str(row.id),
        "channel": row.channel,
        "template_code": row.template_code,
        "recipient": row.recipient,
        "recipient_name": recipient_name,
        "recipient_avatar_url": None,
        "subject": row.subject,
        "body": row.body,
        "status": row.status,
        "provider": row.provider,
        "provider_message_id": row.provider_message_id,
        "attempt_count": row.attempt_count,
        "max_attempts": row.max_attempts,
        "last_error_code": row.last_error_code,
        "last_error_message": row.last_error_message,
        "sent_at": row.sent_at,
        "related_resource": row.related_resource,
        "related_resource_id": str(row.related_resource_id) if row.related_resource_id else None,
        "customer_id": str(row.customer_id) if row.customer_id else None,
        "job_id": row.job_id,
        "created_at": row.created_at,
        "updated_at": row.updated_at,
    }


async def enrich_public(
    session: AsyncSession,
    ctx: SecurityContext,
    rows: list[Notification],
) -> list[dict[str, Any]]:
    items = [to_public(row) for row in rows]
    if not items or not ctx.tenant_id:
        return items

    emails: set[str] = set()
    phones: set[str] = set()
    customer_ids: set[UUID] = set()
    for row in rows:
        recipient = (row.recipient or "").strip()
        channel = (row.channel or "").upper()
        if channel == NotificationChannel.EMAIL.value and "@" in recipient:
            emails.add(recipient.lower())
        elif recipient:
            phones.add(recipient)
        if row.customer_id:
            customer_ids.add(row.customer_id)

    user_by_email: dict[str, User] = {}
    if emails:
        users = (
            await session.execute(
                select(User).where(
                    User.tenant_id == ctx.tenant_id,
                    User.deleted_at.is_(None),
                    func.lower(User.email).in_(list(emails)),
                )
            )
        ).scalars().all()
        for user in users:
            user_by_email[(user.email or "").lower()] = user

    customer_by_id: dict[UUID, Customer] = {}
    customer_by_email: dict[str, Customer] = {}
    customer_by_phone: dict[str, Customer] = {}
    clauses = []
    if customer_ids:
        clauses.append(Customer.id.in_(list(customer_ids)))
    if emails:
        clauses.append(func.lower(Customer.email).in_(list(emails)))
    if phones:
        clauses.append(Customer.phone.in_(list(phones)))
    if clauses:
        customers = (
            await session.execute(
                select(Customer).where(
                    Customer.tenant_id == ctx.tenant_id,
                    Customer.deleted_at.is_(None),
                    or_(*clauses),
                )
            )
        ).scalars().all()
        for customer in customers:
            customer_by_id[customer.id] = customer
            if customer.email:
                customer_by_email[customer.email.lower()] = customer
            if customer.phone:
                customer_by_phone[customer.phone] = customer

    for row, item in zip(rows, items, strict=True):
        recipient = (row.recipient or "").strip()
        channel = (row.channel or "").upper()
        name = item.get("recipient_name")
        avatar: str | None = None

        if channel == NotificationChannel.EMAIL.value and recipient:
            user = user_by_email.get(recipient.lower())
            if user:
                name = name or (user.full_name or None)
                avatar = _safe_avatar_url(user.avatar_url)
            if not avatar or not name:
                customer = customer_by_email.get(recipient.lower())
                if customer:
                    name = name or _customer_display_name(customer)
                    avatar = avatar or _safe_avatar_url(customer.avatar_url)
        else:
            customer = None
            if row.customer_id:
                customer = customer_by_id.get(row.customer_id)
            if customer is None and recipient:
                customer = customer_by_phone.get(recipient)
            if customer is not None:
                name = name or _customer_display_name(customer)
                avatar = _safe_avatar_url(customer.avatar_url)

        item["recipient_name"] = name
        item["recipient_avatar_url"] = avatar

    return items


class NotificationService:
    def __init__(self, session: AsyncSession, ctx: SecurityContext) -> None:
        self.session = session
        self.ctx = ctx
        self.repo = NotificationRepository(session, ctx)
        self.audit = AuditService(session)
        self.jobs = JobService(session, ctx)
        self.idempotency = IdempotencyService(session)

    async def list(
        self,
        *,
        page: int,
        limit: int,
        query: str | None,
        status: str | None,
        channel: str | None,
    ) -> tuple[list[Notification], int]:
        return await self.repo.search(
            query=query,
            status=status,
            channel=channel,
            offset=(page - 1) * limit,
            limit=limit,
        )

    async def get(self, notification_id: UUID) -> Notification:
        row = await self.repo.get(notification_id)
        self.ctx.assert_branch_access(getattr(row, "branch_id", None))
        return row

    def templates(self) -> list[str]:
        return list_template_codes()

    async def send(
        self,
        body: NotificationSendRequest,
        *,
        idempotency_key: str | None = None,
        from_staff: bool = True,
        actor_branch_id: UUID | None = None,
    ) -> Notification | dict[str, Any]:
        self.ctx.require_active_tenant()
        channel = body.channel.upper()
        if channel not in {
            NotificationChannel.SMS.value,
            NotificationChannel.EMAIL.value,
            NotificationChannel.WHATSAPP.value,
        }:
            raise ValidationAppError("Supported channels: SMS, EMAIL, WHATSAPP")

        from app.modules.system_config.service import SystemConfigService

        cfg = SystemConfigService(self.session)
        await cfg.require_outbound(channel)

        template_code = body.template_code.upper()
        if from_staff:
            if not is_staff_template(template_code):
                raise ValidationAppError("That notification template is not available")
        elif not is_known_template(template_code):
            raise ValidationAppError("That notification template is not available")
        if from_staff and body.customer_id is None:
            raise ValidationAppError("Notifications must be sent to a customer of this agency")

        branch_id = None
        if body.customer_id is not None:
            from app.modules.customers.repository import CustomerRepository

            customer = await CustomerRepository(self.session, self.ctx).get_active_by_id(
                body.customer_id
            )
            recipient = body.recipient.strip()
            allowed = {
                item.lower()
                for item in ((customer.phone or "").strip(), (customer.email or "").strip())
                if item
            }
            if recipient.lower() not in allowed:
                raise ValidationAppError(
                    "Recipient must be the phone or email on the selected customer record"
                )
            preferred = actor_branch_id or getattr(customer, "branch_id", None)
            if from_staff:
                from app.core.security.branch_scope import resolve_authorized_branch

                branch_id = await resolve_authorized_branch(
                    self.ctx, self.session, preferred
                )
            else:
                from app.core.security.branch_scope import resolve_transactional_branch

                branch_id = await resolve_transactional_branch(
                    self.ctx, self.session, preferred
                )
        else:
            recipient = body.recipient.strip()
            if from_staff:
                if actor_branch_id is not None:
                    branch_id = actor_branch_id
            else:
                from app.core.security.branch_scope import resolve_transactional_branch

                branch_id = await resolve_transactional_branch(
                    self.ctx, self.session, actor_branch_id
                )

        if from_staff:
            since = datetime.now(UTC) - timedelta(hours=1)
            if await self.repo.count_since(since=since) >= _STAFF_SEND_CAP_PER_HOUR:
                raise ValidationAppError("Notification send limit reached for this hour")

        context = sanitize_template_context(body.context)

        payload = {
            "channel": channel,
            "template_code": template_code,
            "recipient": recipient,
            "context": context,
            "customer_id": str(body.customer_id) if body.customer_id else None,
            "related_resource": body.related_resource,
            "related_resource_id": str(body.related_resource_id)
            if body.related_resource_id
            else None,
        }
        idem_record: IdempotencyKey | None = None
        if idempotency_key:
            started = await self.idempotency.begin(
                tenant_id=self.ctx.tenant_id,
                user_id=self.ctx.user_id,
                key=idempotency_key,
                operation="notification.send",
                request_hash=IdempotencyService.hash_request(payload),
            )
            if isinstance(started, dict):
                return started
            idem_record = started

        subject, rendered_body = render_template(template_code, context, channel=channel)
        job_key = None
        job = None
        if from_staff:
            job = await self.jobs.create(
                tenant_id=self.ctx.tenant_id,
                user_id=self.ctx.user_id,
                job_type=JobType.NOTIFICATION,
            )
            job_key = job.job_key
        notification = Notification(
            tenant_id=self.ctx.tenant_id,
            created_by_user_id=self.ctx.actor_user_id,
            customer_id=body.customer_id,
            branch_id=branch_id,
            related_resource=body.related_resource,
            related_resource_id=body.related_resource_id,
            channel=channel,
            template_code=template_code,
            recipient=recipient,
            subject=subject,
            body=rendered_body,
            context_json=context,
            status=NotificationStatus.QUEUED.value,
            priority=template_priority(template_code),
            provider="PENDING",
            job_id=job_key,
            idempotency_key=idempotency_key,
        )
        await self.repo.add(notification)
        await self.session.flush()
        if job is not None:
            await self.jobs.transition(job, JobStatus.QUEUED)
        await self.audit.record(
            action="notification.queued",
            resource="notification",
            resource_id=str(notification.id),
            tenant_id=self.ctx.tenant_id,
            user_id=self.ctx.user_id,
            metadata={
                "channel": channel,
                "template": notification.template_code,
                "recipient": notification.recipient,
            },
        )

        settings = get_settings()
        background = (
            channel == NotificationChannel.EMAIL.value and settings.email_async_delivery
        ) or (channel == NotificationChannel.SMS.value and settings.sms_async_delivery)
        if body.deliver_now and not background:
            await self.deliver(notification.id)
        elif body.deliver_now:
            wakeup_email_dispatcher()

        public = to_public(notification)
        if idem_record is not None:
            await self.idempotency.complete(
                idem_record, response_body=public, job_id=notification.job_id
            )
        return notification

    async def deliver(self, notification_id: UUID) -> Notification:
        """Attempt delivery (or retry). No blind infinite retries."""
        self.ctx.require_active_tenant()
        notification = await self.repo.get(notification_id)
        self.ctx.assert_branch_access(getattr(notification, "branch_id", None))
        if notification.status == NotificationStatus.SENT.value:
            return notification
        if notification.status == NotificationStatus.CANCELLED.value:
            raise ValidationAppError("Notification was cancelled")
        if notification.attempt_count >= notification.max_attempts:
            notification.status = NotificationStatus.FAILED.value
            await self.session.flush()
            raise ValidationAppError("Notification exceeded max delivery attempts")

        from app.modules.system_config.service import SystemConfigService

        if not await SystemConfigService(self.session).outbound_allowed(
            notification.channel, live=True
        ):
            notification.status = NotificationStatus.QUEUED.value
            notification.last_error_code = "CHANNEL_DISABLED"
            notification.last_error_message = (
                f"{notification.channel} is switched off in system settings"
            )
            notification.next_retry_at = None
            await self.session.flush()
            return notification

        job = None
        if notification.job_id:
            try:
                job = await self.jobs.get_authorized(notification.job_id)
            except Exception:
                job = None

        notification.status = NotificationStatus.SENDING.value
        notification.attempt_count += 1
        await self.session.flush()
        if job:
            await self.jobs.transition(job, JobStatus.RUNNING)
            await self.jobs.add_event(
                job,
                "EXTERNAL_REQUEST_STARTED",
                message=f"notify:{notification.channel}",
            )

        provider = get_notification_provider(notification.channel)
        result = await provider.send(
            recipient=notification.recipient,
            subject=notification.subject,
            body=notification.body,
            metadata={
                "template": notification.template_code,
                "notification_id": str(notification.id),
                "tenant_id": str(notification.tenant_id),
                "context": dict(notification.context_json or {}),
                "attachments": attachments_metadata(notification),
            },
        )
        notification.provider = result.provider_name
        notification.provider_payload = result.raw

        if result.success:
            notification.status = NotificationStatus.SENT.value
            notification.provider_message_id = result.provider_message_id
            notification.sent_at = datetime.now(UTC)
            notification.last_error_code = None
            notification.last_error_message = None
            notification.next_retry_at = None
            if is_otp_template(notification.template_code):
                notification.body = redact_otp_from_body(
                    notification.body, notification.context_json
                )
                notification.context_json = redact_sensitive_context(notification.context_json)
            await self.session.flush()
            if job:
                await self.jobs.add_event(job, "EXTERNAL_RESPONSE_RECEIVED", message="sent")
                await self.jobs.transition(job, JobStatus.COMPLETED)
            await self.audit.record(
                action="notification.sent",
                resource="notification",
                resource_id=str(notification.id),
                tenant_id=self.ctx.tenant_id,
                user_id=self.ctx.user_id,
                metadata={"provider_message_id": result.provider_message_id},
            )
            return notification

        notification.last_error_code = result.error_code
        notification.last_error_message = result.error_message
        permanent = result.error_code in {
            "AUTH_FAILED",
            "REJECTED",
            "INVALID_RECIPIENT",
            "NOT_CONFIGURED",
        }
        if permanent or notification.attempt_count >= notification.max_attempts:
            notification.status = NotificationStatus.FAILED.value
            notification.next_retry_at = None
            if job:
                await self.jobs.transition(
                    job,
                    JobStatus.FAILED,
                    error_code=result.error_code,
                    error_message=result.error_message,
                )
        else:
            notification.status = NotificationStatus.QUEUED.value
            backoff = _RETRY_BACKOFF[min(notification.attempt_count - 1, len(_RETRY_BACKOFF) - 1)]
            notification.next_retry_at = datetime.now(UTC) + timedelta(seconds=backoff)
            if job:
                await self.jobs.transition(
                    job,
                    JobStatus.RETRYING,
                    error_code=result.error_code,
                    error_message=result.error_message,
                )
        await self.session.flush()
        await self.audit.record(
            action="notification.delivery_failed",
            resource="notification",
            resource_id=str(notification.id),
            tenant_id=self.ctx.tenant_id,
            user_id=self.ctx.user_id,
            result="FAILURE",
            metadata={"code": result.error_code, "attempt": notification.attempt_count},
        )
        return notification

    async def cancel(self, notification_id: UUID) -> Notification:
        self.ctx.require_active_tenant()
        notification = await self.repo.get(notification_id)
        self.ctx.assert_branch_access(getattr(notification, "branch_id", None))
        if notification.status == NotificationStatus.SENT.value:
            raise ValidationAppError("Cannot cancel a sent notification")
        notification.status = NotificationStatus.CANCELLED.value
        await self.session.flush()
        await self.audit.record(
            action="notification.cancel",
            resource="notification",
            resource_id=str(notification.id),
            tenant_id=self.ctx.tenant_id,
            user_id=self.ctx.user_id,
        )
        return notification

    async def enqueue_system(
        self,
        *,
        channel: str,
        template_code: str,
        recipient: str,
        context: dict[str, Any],
        related_resource: str | None = None,
        related_resource_id: UUID | None = None,
        customer_id: UUID | None = None,
        deliver_now: bool = True,
    ) -> Notification | None:
        """Fire-and-forget helper for domain events (skips if recipient empty)."""
        if not recipient or not recipient.strip():
            return None
        body = NotificationSendRequest(
            channel=channel,
            template_code=template_code,
            recipient=recipient.strip(),
            context=context,
            related_resource=related_resource,
            related_resource_id=related_resource_id,
            customer_id=customer_id,
            deliver_now=deliver_now,
        )
        result = await self.send(body, from_staff=False)
        return result if isinstance(result, Notification) else None

    async def enqueue_transactional(
        self,
        *,
        channel: str,
        template_code: str,
        recipient: str,
        context: dict[str, Any],
        related_resource: str | None = None,
        related_resource_id: UUID | None = None,
        customer_id: UUID | None = None,
        deliver_now: bool = True,
        branch_id: UUID | None = None,
    ) -> Notification | None:
        """OTP / account mail — no customer match required. Best-effort."""
        if not recipient or not recipient.strip():
            return None
        body = NotificationSendRequest(
            channel=channel,
            template_code=template_code,
            recipient=recipient.strip(),
            context=context,
            related_resource=related_resource,
            related_resource_id=related_resource_id,
            customer_id=customer_id,
            deliver_now=deliver_now,
        )
        result = await self.send(body, from_staff=False, actor_branch_id=branch_id)
        return result if isinstance(result, Notification) else None

    async def send_otp_email(
        self,
        *,
        recipient: str,
        code: str,
        minutes: int = 10,
        recipient_name: str = "",
        template_code: str = "OTP_CODE",
    ) -> Notification | None:
        """Queue a branded OTP email. The code is redacted after a successful send."""
        return await self.enqueue_transactional(
            channel=NotificationChannel.EMAIL.value,
            template_code=template_code,
            recipient=recipient,
            context={
                "otp_code": code,
                "otp_minutes": str(minutes),
                "recipient_name": recipient_name,
            },
        )
