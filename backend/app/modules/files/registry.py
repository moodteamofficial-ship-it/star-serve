"""Write generated PDFs to disk and keep a detailed Postgres copy of the link."""

from __future__ import annotations

import hashlib
from datetime import UTC, datetime
from typing import Any
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import get_settings
from app.core.logging.context import get_request_id
from app.core.security.context import SecurityContext
from app.core.storage import get_blob_store
from app.modules.files.enums import StoredFileAccessKind, StoredFileKind, StoredFileSource
from app.modules.files.models import StoredFile, StoredFileAccess
from app.modules.notifications.pdf_store import StoredMailPdf, relative_mail_path, store_mail_pdf


def _mail_storage_label() -> str:
    backend = (get_settings().storage_backend or "local").strip().lower()
    return "gcs" if backend == "gcs" else "email-pdfs"


def to_public(row: StoredFile) -> dict[str, Any]:
    """Staff-safe projection. Absolute filesystem paths never leave the server."""
    return {
        "id": str(row.id),
        "kind": row.kind,
        "resource_id": str(row.resource_id),
        "filename": row.filename,
        "relative_path": row.relative_path,
        "storage": row.storage,
        "content_type": row.content_type,
        "content_sha256": row.content_sha256,
        "file_size_bytes": row.file_size_bytes,
        "created_by_user_id": str(row.created_by_user_id) if row.created_by_user_id else None,
        "created_by_label": row.created_by_label,
        "source": row.source,
        "generate_count": int(row.generate_count or 0),
        "view_count": int(row.view_count or 0),
        "download_count": int(row.download_count or 0),
        "email_count": int(row.email_count or 0),
        "last_generated_at": row.last_generated_at.isoformat() if row.last_generated_at else None,
        "last_viewed_at": row.last_viewed_at.isoformat() if row.last_viewed_at else None,
        "last_viewed_by_user_id": (
            str(row.last_viewed_by_user_id) if row.last_viewed_by_user_id else None
        ),
        "last_downloaded_at": (
            row.last_downloaded_at.isoformat() if row.last_downloaded_at else None
        ),
        "last_downloaded_by_user_id": (
            str(row.last_downloaded_by_user_id) if row.last_downloaded_by_user_id else None
        ),
        "last_emailed_at": row.last_emailed_at.isoformat() if row.last_emailed_at else None,
        "created_at": row.created_at.isoformat() if row.created_at else None,
        "updated_at": row.updated_at.isoformat() if row.updated_at else None,
    }


def _actor_label(ctx: SecurityContext) -> str:
    if ctx.is_guest:
        return "Client"
    return (ctx.actor_display_name or ctx.email or "").strip() or "Staff"


def _source(ctx: SecurityContext, explicit: str | None) -> str:
    if explicit:
        return explicit
    return StoredFileSource.GUEST_SUBMIT.value if ctx.is_guest else StoredFileSource.STAFF.value


async def persist_mail_pdf(
    session: AsyncSession,
    ctx: SecurityContext,
    *,
    kind: str,
    resource_id: UUID,
    content: bytes,
    filename: str,
    access_kind: str,
    customer_id: UUID | None = None,
    source: str | None = None,
    write_bytes: bool = True,
    ip_address: str | None = None,
    user_agent: str | None = None,
    metadata: dict[str, Any] | None = None,
) -> StoredFile | None:
    """Save the PDF under data/email-pdfs and upsert the registry row.

    Bytes are written at most once for identical content (BlobStore
    ``skip_identical``). Registry counters still update on every access.
    """
    digest = hashlib.sha256(content).hexdigest()
    row = await session.scalar(
        select(StoredFile).where(
            StoredFile.tenant_id == ctx.tenant_id,
            StoredFile.kind == kind,
            StoredFile.resource_id == resource_id,
        )
    )
    should_write = write_bytes
    if should_write and row is not None and row.content_sha256 == digest:
        try:
            key = relative_mail_path(
                tenant_id=ctx.tenant_id, kind=kind, resource_id=resource_id
            )
            if get_blob_store().exists(namespace="email-pdfs", relative_key=key):
                should_write = False
        except ValueError:
            pass

    disk: StoredMailPdf | None = None
    if should_write:
        disk = store_mail_pdf(
            tenant_id=ctx.tenant_id,
            kind=kind,
            resource_id=resource_id,
            content=content,
            filename=filename,
        )
    now = datetime.now(UTC)
    actor = ctx.actor_user_id
    label = _actor_label(ctx)
    origin = _source(ctx, source)
    if row is None:
        if disk is None:
            return None
        row = StoredFile(
            tenant_id=ctx.tenant_id,
            branch_id=getattr(ctx, "home_branch_id", None),
            customer_id=customer_id,
            kind=kind if kind in {item.value for item in StoredFileKind} else StoredFileKind.CLAIM.value,
            resource_id=resource_id,
            relative_path=disk.relative_path,
            storage=_mail_storage_label(),
            filename=disk.filename,
            content_type="application/pdf",
            content_sha256=disk.sha256,
            file_size_bytes=disk.size_bytes,
            created_by_user_id=actor,
            created_by_label=label,
            source=origin,
            generate_count=1,
            last_generated_at=now,
            last_generated_by_user_id=actor,
        )
        session.add(row)
        await session.flush()
    else:
        if disk is not None:
            row.relative_path = disk.relative_path
            row.filename = disk.filename
            row.content_sha256 = disk.sha256
            row.file_size_bytes = disk.size_bytes
            row.generate_count = int(row.generate_count or 0) + 1
            row.last_generated_at = now
            row.last_generated_by_user_id = actor
        if customer_id and row.customer_id is None:
            row.customer_id = customer_id
        if actor and row.created_by_user_id is None:
            row.created_by_user_id = actor
        if label and not row.created_by_label:
            row.created_by_label = label

    kind_norm = (access_kind or "").upper()
    if kind_norm == StoredFileAccessKind.VIEW.value:
        row.view_count = int(row.view_count or 0) + 1
        row.last_viewed_at = now
        row.last_viewed_by_user_id = actor
    elif kind_norm == StoredFileAccessKind.DOWNLOAD.value:
        row.download_count = int(row.download_count or 0) + 1
        row.last_downloaded_at = now
        row.last_downloaded_by_user_id = actor
    elif kind_norm == StoredFileAccessKind.EMAIL.value:
        row.email_count = int(row.email_count or 0) + 1
        row.last_emailed_at = now

    session.add(
        StoredFileAccess(
            tenant_id=ctx.tenant_id,
            stored_file_id=row.id,
            resource_id=resource_id,
            user_id=actor,
            actor_label=label,
            access_kind=kind_norm or StoredFileAccessKind.STORED.value,
            source=origin,
            relative_path=row.relative_path,
            content_sha256=row.content_sha256,
            file_size_bytes=row.file_size_bytes,
            ip_address=ip_address,
            user_agent=(user_agent or "")[:512] or None,
            request_id=get_request_id(),
            metadata_json=metadata or {},
        )
    )
    await session.flush()
    return row