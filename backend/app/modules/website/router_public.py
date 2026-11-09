"""Public website content — published material only."""

from __future__ import annotations

from typing import Annotated

from fastapi import APIRouter, Depends, Request
from fastapi.responses import JSONResponse, Response
from pydantic import BaseModel, EmailStr, Field
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.dependencies.auth import get_db
from app.core.exceptions import ResourceNotFoundError
from app.core.responses import success_response
from app.modules.website.media import read_website_media
from app.modules.website.service import WebsiteCmsService

router = APIRouter(prefix="/website", tags=["Website"])


@router.get("/media/{media_key}")
async def website_media(media_key: str) -> Response:
    stored = read_website_media(media_key)
    if stored is None:
        raise ResourceNotFoundError("Media not found")
    payload, content_type = stored
    return Response(
        content=payload,
        media_type=content_type,
        headers={"Cache-Control": "public, max-age=86400"},
    )


@router.get("/bootstrap")
async def website_bootstrap(
    request: Request,
    db: Annotated[AsyncSession, Depends(get_db)],
) -> JSONResponse:
    service = WebsiteCmsService(db)
    data = await service.bootstrap_public()
    await db.commit()
    payload = success_response(data, request_id=getattr(request.state, "request_id", None))
    return JSONResponse(
        content=payload,
        headers={"Cache-Control": "public, max-age=30, stale-while-revalidate=120"},
    )


@router.get("/pages/{slug}")
async def website_page(
    slug: str,
    request: Request,
    db: Annotated[AsyncSession, Depends(get_db)],
) -> JSONResponse:
    service = WebsiteCmsService(db)
    data = await service.page_public(slug.strip().lower())
    await db.commit()
    payload = success_response(data, request_id=getattr(request.state, "request_id", None))
    return JSONResponse(
        content=payload,
        headers={"Cache-Control": "public, max-age=30, stale-while-revalidate=120"},
    )


class EnquiryRequest(BaseModel):
    full_name: str = Field(min_length=2, max_length=120)
    phone: str = Field(min_length=9, max_length=32)
    email: EmailStr | None = None
    cover_needed: str | None = Field(default=None, max_length=120)
    message: str | None = Field(default=None, max_length=2000)
    website: str | None = Field(default=None, max_length=200)  # honeypot — bots only

    model_config = {"extra": "forbid"}


@router.post("/enquiries")
async def submit_enquiry(
    body: EnquiryRequest,
    request: Request,
    db: Annotated[AsyncSession, Depends(get_db)],
) -> dict:
    if body.website:
        return success_response({"received": True}, message="Thank you", request_id=None)
    service = WebsiteCmsService(db)
    row = await service.create_enquiry(
        full_name=body.full_name,
        phone=body.phone,
        email=str(body.email) if body.email else None,
        cover_needed=body.cover_needed,
        message=body.message,
    )
    await db.commit()
    return success_response(
        {"id": str(row.id)},
        message="We received your enquiry and will respond soon.",
        request_id=getattr(request.state, "request_id", None),
    )
