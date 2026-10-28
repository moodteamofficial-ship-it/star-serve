"""Email a downloaded claim or certificate PDF to the customer and staff."""

from __future__ import annotations

from typing import Any
from uuid import UUID

from sqlalchemy.ext.asyncio import AsyncSession

from app.core.exceptions import (
    AuthorizationError,
    ResourceNotFoundError,
    ServiceDisabledError,
    TenantAccessError,
    ValidationAppError,
)
from app.core.logging import get_logger
from app.core.security.context import SecurityContext
from app.integrations.notifications.email.message import EmailAttachment
from app.modules.customers.models import Customer
from app.modules.files.enums import StoredFileAccessKind
from app.modules.files.registry import persist_mail_pdf
from app.modules.notifications.enums import NotificationChannel, NotificationTemplate
from app.modules.notifications.models import Notification
from app.modules.notifications.pdf_store import read_mail_pdf

logger = get_logger(__name__)

_GUEST_MAILBOX = "guest@starserve.local"
_PDF_TEMPLATES = frozenset(
    {
        NotificationTemplate.CLAIM_PDF.value,
        NotificationTemplate.CLAIM_RECEIVED.value,
        NotificationTemplate.CERTIFICATE_PDF.value,
    }
)
_KIND_BY_TEMPLATE = {
    NotificationTemplate.CLAIM_PDF.value: "claim",
    NotificationTemplate.CLAIM_RECEIVED.value: "claim",
    NotificationTemplate.CERTIFICATE_PDF.value: "certificate",
}


_AGENT_QR_TEMPLATES = frozenset(
    {
        NotificationTemplate.AGENT_REGISTERED.value,
        NotificationTemplate.AGENT_APPROVED.value,
    }
)


def _agent_qr_attachments(row: Notification) -> list[EmailAttachment]:
    """QR card for agent kit mail: once inline for the body, once to download."""
    context = row.context_json or {}
    agent_code = str(context.get("agent_code") or "").strip()
    if not agent_code:
        return []
    from app.integrations.notifications.email.renderer import AGENT_QR_CID
    from app.modules.intermediaries.agent_qr import agent_qr_filename, build_agent_qr_card_png

    try:
        png = build_agent_qr_card_png(
            agent_name=str(context.get("recipient_name") or ""), agent_code=agent_code
        )
    except Exception:
        logger.warning("agent_qr_render_failed", extra={"notification_id": str(row.id)})
        return []
    filename = agent_qr_filename(agent_code)
    return [
        EmailAttachment(
            filename=filename,
            content=png,
            content_type="image/png",
            content_id=AGENT_QR_CID,
            inline=True,
        ),
        EmailAttachment(filename=filename, content=png, content_type="image/png"),
    ]


def _referral_qr_attachments(row: Notification) -> list[EmailAttachment]:
    """QR card for customer referral kit mail: inline + downloadable."""
    context = row.context_json or {}
    referral_code = str(context.get("referral_code") or "").strip()
    if not referral_code:
        return []
    from app.integrations.notifications.email.renderer import AGENT_QR_CID
    from app.modules.intermediaries.agent_qr import (
        build_referral_qr_card_png,
        referral_qr_filename,
    )

    try:
        png = build_referral_qr_card_png(
            holder_name=str(context.get("recipient_name") or ""),
            referral_code=referral_code,
        )
    except Exception:
        logger.warning("referral_qr_render_failed", extra={"notification_id": str(row.id)})
        return []
    filename = referral_qr_filename(referral_code)
    return [
        EmailAttachment(
            filename=filename,
            content=png,
            content_type="image/png",
            content_id=AGENT_QR_CID,
            inline=True,
        ),
        EmailAttachment(filename=filename, content=png, content_type="image/png"),
    ]


def attachments_for_notification(row: Notification) -> list[EmailAttachment]:
    """Load the PDF written at download time. Missing files send without a file."""
    code = (row.template_code or "").upper()
    if code in _AGENT_QR_TEMPLATES:
        return _agent_qr_attachments(row)
    if code == NotificationTemplate.CUSTOMER_REFERRAL_KIT.value:
        return _referral_qr_attachments(row)
    if code not in _PDF_TEMPLATES:
        return []
    kind = _KIND_BY_TEMPLATE.get(code)
    resource_id = row.related_resource_id
    if kind is None or resource_id is None or (row.related_resource or "") != kind:
        return []
    packed = read_mail_pdf(
        tenant_id=row.tenant_id,
        kind=kind,
        resource_id=resource_id,
    )
    if packed is None:
        logger.warning(
            "mail_pdf_missing",
            extra={"template": code, "resource_id": str(resource_id)},
        )
        return []
    content, filename = packed
    return [
        EmailAttachment(
            filename=filename,
            content=content,
            content_type="application/pdf",
        )
    ]


def attachments_metadata(row: Notification) -> list[dict[str, Any]]:
    return [
        {
            "filename": item.filename,
            "content": item.content,
            "content_type": item.content_type,
            "content_id": item.content_id,
            "inline": item.inline,
        }
        for item in attachments_for_notification(row)
    ]


async def enqueue_downloaded_pdf_emails(
    session: AsyncSession,
    ctx: SecurityContext,
    *,
    kind: str,
    resource_id: UUID,
    customer_id: UUID | None,
    content: bytes,
    filename: str,
    context: dict[str, Any],
    already_stored: bool = False,
) -> None:
    """Best-effort: never fail the download if mail cannot be queued."""
    template = (
        NotificationTemplate.CLAIM_PDF.value
        if kind == "claim"
        else NotificationTemplate.CERTIFICATE_PDF.value
    )
    try:
        await _enqueue_downloaded_pdf_emails(
            session,
            ctx,
            kind=kind,
            resource_id=resource_id,
            customer_id=customer_id,
            content=content,
            filename=filename,
            context=context,
            template=template,
            already_stored=already_stored,
        )
    except Exception:
        logger.warning(
            "mail_pdf_enqueue_failed",
            extra={"template": template, "kind": kind, "resource_id": str(resource_id)},
            exc_info=True,
        )


async def _enqueue_downloaded_pdf_emails(
    session: AsyncSession,
    ctx: SecurityContext,
    *,
    kind: str,
    resource_id: UUID,
    customer_id: UUID | None,
    content: bytes,
    filename: str,
    context: dict[str, Any],
    template: str,
    already_stored: bool = False,
) -> None:
    try:
        await persist_mail_pdf(
            session,
            ctx,
            kind=kind,
            resource_id=resource_id,
            content=content,
            filename=filename,
            access_kind=StoredFileAccessKind.EMAIL.value,
            customer_id=customer_id,
            write_bytes=not already_stored,
            metadata={"template": template},
        )
    except Exception:
        logger.warning(
            "mail_pdf_registry_failed",
            extra={"kind": kind, "resource_id": str(resource_id)},
            exc_info=True,
        )
        if not already_stored:
            from app.modules.notifications.pdf_store import store_mail_pdf

            store_mail_pdf(
                tenant_id=ctx.tenant_id,
                kind=kind,
                resource_id=resource_id,
                content=content,
                filename=filename,
            )

    customer_email = ""
    recipient_name = (context.get("recipient_name") or "").strip()
    customer: Customer | None = None
    if customer_id is not None:
        customer = await session.get(Customer, customer_id)
        if customer is not None and customer.tenant_id == ctx.tenant_id:
            customer_email = (customer.email or "").strip()
            if not recipient_name:
                recipient_name = " ".join(
                    part for part in (customer.first_name, customer.last_name) if part
                ).strip()
        else:
            customer = None

    payload = {**context, "recipient_name": recipient_name}
    from app.modules.notifications.service import NotificationService

    notify = NotificationService(session, ctx)
    targets: list[tuple[str, UUID | None]] = []
    if customer is not None and customer_email and "@" in customer_email:
        targets.append((customer_email, customer.id))
    staff_email = _staff_mailbox(ctx)
    if staff_email and staff_email.lower() not in {item[0].lower() for item in targets}:
        targets.append((staff_email, None))

    for recipient, cid in targets:
        try:
            if cid is None:
                await notify.enqueue_transactional(
                    channel=NotificationChannel.EMAIL.value,
                    template_code=template,
                    recipient=recipient,
                    context=payload,
                    related_resource=kind,
                    related_resource_id=resource_id,
                    branch_id=getattr(ctx, "home_branch_id", None),
                )
            else:
                await notify.enqueue_system(
                    channel=NotificationChannel.EMAIL.value,
                    template_code=template,
                    recipient=recipient,
                    context=payload,
                    related_resource=kind,
                    related_resource_id=resource_id,
                    customer_id=cid,
                )
        except (
            ServiceDisabledError,
            ValidationAppError,
            ResourceNotFoundError,
            TenantAccessError,
            AuthorizationError,
        ):
            continue
        except Exception:
            logger.warning(
                "mail_pdf_enqueue_failed",
                extra={"template": template, "kind": kind},
                exc_info=True,
            )


def _staff_mailbox(ctx: SecurityContext) -> str:
    if ctx.is_guest:
        return ""
    email = (ctx.email or "").strip()
    if not email or "@" not in email:
        return ""
    if email.lower() == _GUEST_MAILBOX:
        return ""
    return email
