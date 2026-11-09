"""Website CMS business logic."""

from __future__ import annotations

import time
from datetime import UTC, datetime
from typing import Any
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.exceptions import ResourceNotFoundError, ValidationAppError
from app.core.security.context import SecurityContext
from app.modules.website.models import (
    WebsiteAdminAudit,
    WebsiteContentState,
    WebsiteEnquiry,
    WebsiteNavigationItem,
    WebsitePage,
    WebsiteSection,
)
from app.modules.website.seed import ensure_website_seed

# Short in-process cache for public marketing reads (avoids remote DB RTT on warm traffic).
_BOOTSTRAP_CACHE: dict[str, Any] | None = None
_BOOTSTRAP_CACHE_AT = 0.0
_BOOTSTRAP_CACHE_VERSION: int | None = None
_PAGE_CACHE: dict[str, tuple[float, int, dict[str, Any]]] = {}
_PUBLIC_CACHE_TTL_SECONDS = 45.0


def invalidate_website_public_cache() -> None:
    global _BOOTSTRAP_CACHE, _BOOTSTRAP_CACHE_AT, _BOOTSTRAP_CACHE_VERSION, _PAGE_CACHE
    _BOOTSTRAP_CACHE = None
    _BOOTSTRAP_CACHE_AT = 0.0
    _BOOTSTRAP_CACHE_VERSION = None
    _PAGE_CACHE = {}


class WebsiteCmsService:
    def __init__(self, session: AsyncSession, ctx: SecurityContext | None = None) -> None:
        self.session = session
        self.ctx = ctx

    async def _state(self, *, seed: bool = True) -> WebsiteContentState:
        if seed:
            await ensure_website_seed(self.session)
        row = await self.session.scalar(select(WebsiteContentState).limit(1))
        if row is None:
            await ensure_website_seed(self.session, force=True)
            row = await self.session.scalar(select(WebsiteContentState).limit(1))
        if row is None:
            raise ValidationAppError("Website content state missing")
        return row

    async def content_version(self) -> int:
        return int((await self._state(seed=False)).content_version)

    async def bootstrap_public(self) -> dict[str, Any]:
        global _BOOTSTRAP_CACHE, _BOOTSTRAP_CACHE_AT, _BOOTSTRAP_CACHE_VERSION

        now = time.monotonic()
        if (
            _BOOTSTRAP_CACHE is not None
            and _BOOTSTRAP_CACHE_VERSION is not None
            and now - _BOOTSTRAP_CACHE_AT < _PUBLIC_CACHE_TTL_SECONDS
        ):
            return dict(_BOOTSTRAP_CACHE)

        state = await self._state(seed=True)
        version = int(state.content_version)
        if (
            _BOOTSTRAP_CACHE is not None
            and _BOOTSTRAP_CACHE_VERSION == version
            and now - _BOOTSTRAP_CACHE_AT < _PUBLIC_CACHE_TTL_SECONDS
        ):
            return dict(_BOOTSTRAP_CACHE)

        nav_rows = await self.session.scalars(
            select(WebsiteNavigationItem)
            .where(WebsiteNavigationItem.enabled.is_(True))
            .order_by(WebsiteNavigationItem.location, WebsiteNavigationItem.sort_order)
        )
        navigation: dict[str, list[dict[str, Any]]] = {"header": [], "footer": []}
        for item in nav_rows:
            bucket = navigation.setdefault(item.location, [])
            bucket.append(
                {
                    "label": item.label,
                    "kind": item.link_kind,
                    "value": item.link_value,
                }
            )

        home_sections = await self._published_sections("home")
        settings = await self._contact_from_sections(home_sections)

        payload = {
            "content_version": version,
            "settings": settings,
            "navigation": navigation,
            "homepage": {"sections": home_sections},
        }
        _BOOTSTRAP_CACHE = payload
        _BOOTSTRAP_CACHE_AT = now
        _BOOTSTRAP_CACHE_VERSION = version
        return dict(payload)

    async def _contact_from_sections(self, sections: list[dict[str, Any]]) -> dict[str, Any]:
        for section in sections:
            if section.get("type") == "contact_strip":
                body = section.get("content") or {}
                return {
                    "location": body.get("location"),
                    "email": body.get("email"),
                    "phone": body.get("phone"),
                }
        return {}

    async def _published_sections(self, page_slug: str) -> list[dict[str, Any]]:
        rows = await self.session.scalars(
            select(WebsiteSection)
            .where(
                WebsiteSection.page_slug == page_slug,
                WebsiteSection.enabled.is_(True),
                WebsiteSection.published_content.is_not(None),
            )
            .order_by(WebsiteSection.sort_order)
        )
        out: list[dict[str, Any]] = []
        for row in rows:
            content = dict(row.published_content or {})
            if row.section_type == "statistics":
                items = content.get("items") or []
                content["items"] = [i for i in items if i.get("verified")]
            if row.section_type == "promo_carousel":
                slides = content.get("slides") or []
                content["slides"] = [
                    slide
                    for slide in slides
                    if isinstance(slide, dict) and slide.get("enabled", True) and slide.get("image_src")
                ]
                if not content["slides"]:
                    continue
            if row.section_type == "partner_showcase":
                partners = content.get("partners") or []
                content["partners"] = [
                    partner
                    for partner in partners
                    if isinstance(partner, dict) and partner.get("enabled", True) and partner.get("name")
                ]
                if not content["partners"]:
                    continue
            if row.section_type == "story_grid":
                posts = content.get("posts") or []
                content["posts"] = [
                    post
                    for post in posts
                    if isinstance(post, dict)
                    and post.get("enabled", True)
                    and post.get("image_src")
                    and post.get("title")
                ]
                if not content["posts"]:
                    continue
            out.append(
                {
                    "key": row.section_key,
                    "type": row.section_type,
                    "variant": row.layout_variant,
                    "content": content,
                }
            )
        return out

    async def page_public(self, slug: str) -> dict[str, Any]:
        now = time.monotonic()
        cached = _PAGE_CACHE.get(slug)
        if cached is not None:
            cached_at, _cached_version, payload = cached
            if now - cached_at < _PUBLIC_CACHE_TTL_SECONDS:
                return dict(payload)

        await ensure_website_seed(self.session)
        page = await self.session.scalar(select(WebsitePage).where(WebsitePage.slug == slug))
        if page is None or not page.published:
            raise ResourceNotFoundError("Page not found")
        version = await self.content_version()
        payload = {
            "slug": page.slug,
            "title": page.title,
            "meta_title": page.meta_title,
            "meta_description": page.meta_description,
            "sections": await self._published_sections(slug),
            "content_version": version,
        }
        _PAGE_CACHE[slug] = (now, version, payload)
        return dict(payload)

    async def admin_overview(self) -> dict[str, Any]:
        await ensure_website_seed(self.session)
        pages = list(await self.session.scalars(select(WebsitePage)))
        sections = list(await self.session.scalars(select(WebsiteSection)))
        published_pages = sum(1 for p in pages if p.published)
        draft_sections = sum(1 for s in sections if s.draft_content != (s.published_content or {}))
        return {
            "content_version": await self.content_version(),
            "pages_total": len(pages),
            "pages_published": published_pages,
            "sections_total": len(sections),
            "sections_with_draft_changes": draft_sections,
        }

    async def list_sections(self, page_slug: str | None = None) -> list[WebsiteSection]:
        stmt = select(WebsiteSection).order_by(WebsiteSection.page_slug, WebsiteSection.sort_order)
        if page_slug:
            stmt = stmt.where(WebsiteSection.page_slug == page_slug)
        return list(await self.session.scalars(stmt))

    async def update_section_draft(
        self, section_id: UUID, *, content: dict[str, Any], enabled: bool | None = None
    ) -> WebsiteSection:
        row = await self.session.get(WebsiteSection, section_id)
        if row is None:
            raise ResourceNotFoundError("Section not found")
        row.draft_content = content
        if enabled is not None:
            row.enabled = enabled
        if self.ctx:
            row.updated_by = self.ctx.user_id
        await self.session.flush()
        return row

    async def publish_all(self) -> int:
        if self.ctx is None:
            raise ValidationAppError("Publishing requires an authenticated admin")
        sections = list(await self.session.scalars(select(WebsiteSection)))
        for row in sections:
            row.published_content = dict(row.draft_content or {})
        state = await self._state()
        state.content_version = int(state.content_version) + 1
        state.last_published_at = datetime.now(UTC)
        state.last_published_by = self.ctx.user_id
        self.session.add(
            WebsiteAdminAudit(
                actor_user_id=self.ctx.user_id,
                action="website.publish",
                detail={"content_version": state.content_version},
            )
        )
        await self.session.flush()
        invalidate_website_public_cache()
        return state.content_version

    async def create_enquiry(
        self,
        *,
        full_name: str,
        phone: str,
        email: str | None,
        cover_needed: str | None,
        message: str | None,
    ) -> WebsiteEnquiry:
        row = WebsiteEnquiry(
            full_name=full_name.strip()[:120],
            phone=phone.strip()[:32],
            email=(email or "").strip()[:254] or None,
            cover_needed=(cover_needed or "").strip()[:120] or None,
            message=(message or "").strip()[:4000] or None,
        )
        self.session.add(row)
        await self.session.flush()
        return row
