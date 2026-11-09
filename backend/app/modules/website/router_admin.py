"""Super Admin website CMS."""

from __future__ import annotations

from typing import Annotated, Any
from uuid import UUID

from fastapi import APIRouter, Depends, File, Request, UploadFile
from pydantic import BaseModel, Field
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.dependencies.auth import get_db, require_permissions
from app.core.responses import success_response
from app.core.security.context import SecurityContext
from app.modules.website.media import store_website_media
from app.modules.website.service import WebsiteCmsService

router = APIRouter(prefix="/website/admin", tags=["Website Admin"])


def _rid(request: Request) -> str | None:
    return getattr(request.state, "request_id", None)


@router.get("/overview")
async def admin_overview(
    request: Request,
    db: Annotated[AsyncSession, Depends(get_db)],
    ctx: Annotated[SecurityContext, Depends(require_permissions("website:read"))],
) -> dict:
    service = WebsiteCmsService(db, ctx)
    data = await service.admin_overview()
    await db.commit()
    return success_response(data, request_id=_rid(request))


@router.get("/sections")
async def list_sections(
    request: Request,
    db: Annotated[AsyncSession, Depends(get_db)],
    ctx: Annotated[SecurityContext, Depends(require_permissions("website:read"))],
    page_slug: str | None = None,
) -> dict:
    service = WebsiteCmsService(db, ctx)
    rows = await service.list_sections(page_slug=page_slug)
    await db.commit()
    items = [
        {
            "id": str(r.id),
            "page_slug": r.page_slug,
            "section_key": r.section_key,
            "section_type": r.section_type,
            "sort_order": r.sort_order,
            "enabled": r.enabled,
            "draft_content": r.draft_content,
            "published_content": r.published_content,
        }
        for r in rows
    ]
    return success_response({"items": items}, request_id=_rid(request))


class SectionUpdateRequest(BaseModel):
    content: dict[str, Any]
    enabled: bool | None = None

    model_config = {"extra": "forbid"}


@router.patch("/sections/{section_id}")
async def update_section(
    section_id: UUID,
    body: SectionUpdateRequest,
    request: Request,
    db: Annotated[AsyncSession, Depends(get_db)],
    ctx: Annotated[SecurityContext, Depends(require_permissions("website:edit"))],
) -> dict:
    service = WebsiteCmsService(db, ctx)
    row = await service.update_section_draft(section_id, content=body.content, enabled=body.enabled)
    await db.commit()
    return success_response(
        {"id": str(row.id), "section_key": row.section_key},
        message="Draft saved",
        request_id=_rid(request),
    )


@router.post("/publish")
async def publish_website(
    request: Request,
    db: Annotated[AsyncSession, Depends(get_db)],
    ctx: Annotated[SecurityContext, Depends(require_permissions("website:publish"))],
) -> dict:
    service = WebsiteCmsService(db, ctx)
    version = await service.publish_all()
    await db.commit()
    return success_response(
        {"content_version": version},
        message="Website published",
        request_id=_rid(request),
    )


@router.post("/media")
async def upload_website_media(
    request: Request,
    db: Annotated[AsyncSession, Depends(get_db)],
    ctx: Annotated[SecurityContext, Depends(require_permissions("website:edit"))],
    file: Annotated[UploadFile, File()],
) -> dict:
    _ = db
    _ = ctx
    payload = await file.read()
    stored = store_website_media(payload)
    return success_response(
        {
            "path": stored.public_path,
            "content_type": stored.content_type,
            "size_bytes": stored.size_bytes,
        },
        message="Image uploaded",
        request_id=_rid(request),
    )
