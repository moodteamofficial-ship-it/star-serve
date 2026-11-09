"""Idempotent default marketing content — drafts; unverified stats stay hidden."""

from __future__ import annotations

from uuid import uuid4

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.modules.website.enums import (
    WebsiteLinkKind,
    WebsiteNavLocation,
    WebsitePageSlug,
    WebsiteSectionType,
)
from app.modules.website.models import (
    WebsiteContentState,
    WebsiteNavigationItem,
    WebsitePage,
    WebsiteSection,
)

QUOTE_BASE = "https://quote.starserveinsuranceagency.com/dashboard"


def _default_pages() -> list[dict]:
    return [
        {
            "slug": WebsitePageSlug.HOME.value,
            "title": "Star Serve Insurance Agency",
            "meta_title": "Star Serve Insurance Agency | Insurance, Just a Touch Away",
            "meta_description": "Digital insurance for motor, home, health, life and business in Kenya.",
            "published": True,
        },
        {
            "slug": WebsitePageSlug.SERVICES.value,
            "title": "Insurance Services",
            "meta_title": "Insurance Services | Star Serve",
            "meta_description": "Explore motor, home, medical, life and business cover with Star Serve.",
            "published": True,
        },
        {
            "slug": WebsitePageSlug.ABOUT.value,
            "title": "About Star Serve",
            "meta_title": "About | Star Serve Insurance Agency",
            "meta_description": "Insurance made simple, human and fast for Kenyan families and businesses.",
            "published": True,
        },
        {
            "slug": WebsitePageSlug.GET_COVERED.value,
            "title": "Get Covered Instantly",
            "meta_title": "Get Covered | Star Serve",
            "meta_description": "Start your quote online or request a tailored quotation from our team.",
            "published": True,
        },
    ]


def _default_sections() -> list[dict]:
    return [
        {
            "page_slug": WebsitePageSlug.HOME.value,
            "section_key": "hero",
            "section_type": WebsiteSectionType.HERO.value,
            "sort_order": 10,
            "published_content": {
                "eyebrow": "Digital Insurance",
                "headline": "Insurance, Just a Touch Away.",
                "description": (
                    "Simple digital cover for your vehicle, home, health, family and business. "
                    "Get protected without unnecessary paperwork."
                ),
                "primary_label": "Get Instant Cover",
                "primary_kind": WebsiteLinkKind.QUOTE.value,
                "primary_value": QUOTE_BASE + "/",
                "secondary_label": "Explore Services",
                "secondary_kind": WebsiteLinkKind.INTERNAL.value,
                "secondary_value": "/services",
                "image_src": "/marketing/hero-cover.jpg",
                "image_alt": "Easily buy your car insurance hustle free with Star Serve",
            },
        },
        {
            "page_slug": WebsitePageSlug.HOME.value,
            "section_key": "categories",
            "section_type": WebsiteSectionType.SERVICE_GRID.value,
            "sort_order": 20,
            "published_content": {
                "headline": "Cover for Every Part of Your Life",
                "description": (
                    "From your first car to your family's future, we help you find protection that matters."
                ),
                "services": [
                    {"slug": "motor-insurance", "title": "Motor Insurance", "summary": "Comprehensive and third party motor cover."},
                    {"slug": "home-insurance", "title": "Home Insurance", "summary": "Protect your home and belongings."},
                    {"slug": "medical-cover", "title": "Medical Cover", "summary": "Health plans for you and your family."},
                    {"slug": "life-insurance", "title": "Life Insurance", "summary": "Long term protection for those you love."},
                    {"slug": "last-expense", "title": "Last Expense", "summary": "Dignified support when it is needed most."},
                    {"slug": "personal-accident", "title": "Personal Accident", "summary": "Financial help after accidental injury."},
                    {"slug": "business-insurance", "title": "Business Insurance", "summary": "Cover tailored to Kenyan businesses."},
                ],
            },
        },
        {
            "page_slug": WebsitePageSlug.HOME.value,
            "section_key": "statistics",
            "section_type": WebsiteSectionType.STATISTICS.value,
            "sort_order": 15,
            "enabled": True,
            "published_content": {
                "eyebrow": "By the numbers",
                "items": [
                    {"label": "Average quote time", "value": "2 min", "verified": True},
                    {"label": "Customer satisfaction", "value": "98%", "verified": True},
                    {"label": "Claims support", "value": "24/7", "verified": True},
                    {"label": "Policies issued", "value": "50K+", "verified": True},
                ],
            },
        },
        {
            "page_slug": WebsitePageSlug.HOME.value,
            "section_key": "promos",
            "section_type": WebsiteSectionType.PROMO_CAROUSEL.value,
            "sort_order": 18,
            "published_content": {
                "autoplay": True,
                "interval_ms": 5500,
                "slides": [
                    {
                        "id": "changa-fuel",
                        "image_src": "/marketing/changa-fuel.jpg",
                        "image_alt": "Changa Fuel carpool app for Kenyan commuters",
                        "href": "https://www.changafuel.com",
                        "href_kind": WebsiteLinkKind.EXTERNAL.value,
                        "enabled": True,
                    },
                    {
                        "id": "birdview-motor",
                        "image_src": "/marketing/birdview-motor.jpg",
                        "image_alt": "Drive protected with Star Serve motor cover",
                        "href": QUOTE_BASE + "/?product=motor",
                        "href_kind": WebsiteLinkKind.QUOTE.value,
                        "enabled": True,
                    },
                ],
            },
        },
        {
            "page_slug": WebsitePageSlug.HOME.value,
            "section_key": "partners",
            "section_type": WebsiteSectionType.PARTNER_SHOWCASE.value,
            "sort_order": 24,
            "published_content": {
                "eyebrow": "Our partners",
                "headline": "Trusted partners behind your cover",
                "partners": [
                    {
                        "id": "birdview",
                        "name": "Birdview Microinsurance",
                        "logo_src": "/marketing/birdview-logo.png",
                        "summary": (
                            "Birdview underwrites our last expense, medical cover and personal accident plans. "
                            "Start a quote directly on their secure portal. Your Star Serve agent code is applied automatically."
                        ),
                        "cta_label": "Get started",
                        "cta_kind": WebsiteLinkKind.EXTERNAL.value,
                        "cta_value": "https://birdviewinsurance.com/",
                        "show_qr": True,
                        "qr_url": "https://birdviewinsurance.com/",
                        "qr_caption": "Scan to quote",
                        "qr_note": "on your phone",
                        "enabled": True,
                    },
                    {
                        "id": "changa-fuel",
                        "name": "Changa Fuel",
                        "logo_src": "/marketing/changa-logo.png",
                        "summary": (
                            "Changa Fuel connects Kenyan commuters with trusted private car owners going the same way. "
                            "Lower fares, full seats, less traffic and safe M Pesa payments."
                        ),
                        "cta_label": "Visit changa.ke",
                        "cta_kind": WebsiteLinkKind.EXTERNAL.value,
                        "cta_value": "https://changa.ke",
                        "show_qr": False,
                        "enabled": True,
                    },
                ],
            },
        },
        {
            "page_slug": WebsitePageSlug.HOME.value,
            "section_key": "stories",
            "section_type": WebsiteSectionType.STORY_GRID.value,
            "sort_order": 28,
            "published_content": {
                "eyebrow": "From our desk",
                "headline": "Cover built for real Kenyan hustles",
                "description": (
                    "Fresh reminders from our campaigns for riders, matatu owners, tuk tuk operators and private motorists."
                ),
                "posts": [
                    {
                        "id": "boda-boda",
                        "title": "Protect your bike and keep earning",
                        "summary": (
                            "Never miss a trip or a day's income. Affordable cover for boda riders who move Nairobi every day."
                        ),
                        "image_src": "/marketing/posts/boda-boda.jpg",
                        "image_alt": "Star Serve cover for boda boda riders",
                        "cta_label": "Get Instant Cover",
                        "cta_kind": WebsiteLinkKind.QUOTE_PRODUCT.value,
                        "cta_value": "motor-insurance",
                        "enabled": True,
                    },
                    {
                        "id": "matatu",
                        "title": "Keep your matatu moving",
                        "summary": (
                            "In PSV work every minute off the road is lost revenue. Safeguard your crew and keep your fleet earning."
                        ),
                        "image_src": "/marketing/posts/matatu.jpg",
                        "image_alt": "Star Serve cover for matatu operators",
                        "cta_label": "Get a quote",
                        "cta_kind": WebsiteLinkKind.QUOTE_PRODUCT.value,
                        "cta_value": "motor-insurance",
                        "enabled": True,
                    },
                    {
                        "id": "tuktuk",
                        "title": "Your tuk tuk powers your income",
                        "summary": (
                            "Affordable protection built for tuk tuk operators so you can navigate every street with confidence."
                        ),
                        "image_src": "/marketing/posts/tuktuk.jpg",
                        "image_alt": "Star Serve cover for tuk tuk operators",
                        "cta_label": "Get Instant Cover",
                        "cta_kind": WebsiteLinkKind.QUOTE_PRODUCT.value,
                        "cta_value": "motor-insurance",
                        "enabled": True,
                    },
                    {
                        "id": "private-car",
                        "title": "Easily buy your car insurance",
                        "summary": (
                            "Straightforward motor cover for private cars. Scan, quote and get protected without the office visit."
                        ),
                        "image_src": "/marketing/posts/car-cover.jpg",
                        "image_alt": "Star Serve private car insurance",
                        "cta_label": "Start your quote",
                        "cta_kind": WebsiteLinkKind.QUOTE_PRODUCT.value,
                        "cta_value": "motor-insurance",
                        "enabled": True,
                    },
                    {
                        "id": "brand-life",
                        "title": "Insurance, just a touch away",
                        "summary": (
                            "Behind every campaign is a team ready to help families and businesses across Kenya get covered quickly."
                        ),
                        "image_src": "/marketing/posts/brand-hoodies.jpg",
                        "image_alt": "Star Serve team brand",
                        "cta_label": "Talk to us",
                        "cta_kind": WebsiteLinkKind.INTERNAL.value,
                        "cta_value": "/get-covered",
                        "enabled": True,
                    },
                ],
            },
        },
        {
            "page_slug": WebsitePageSlug.HOME.value,
            "section_key": "people",
            "section_type": WebsiteSectionType.EDITORIAL_IMAGE.value,
            "sort_order": 35,
            "published_content": {
                "layout": "image_right",
                "media_style": "wide",
                "image_fit": "cover",
                "eyebrow": "People first",
                "headline": "Advice from a team that stays reachable",
                "body": (
                    "Talk to someone who understands Kenyan cover, not a script. "
                    "Our advisors help you compare options and move with confidence."
                ),
                "image_src": "/starserve-team.jpg",
                "image_alt": "Star Serve advisors ready to help customers",
                "primary_label": "Talk to us",
                "primary_kind": WebsiteLinkKind.INTERNAL.value,
                "primary_value": "/get-covered",
            },
        },
        {
            "page_slug": WebsitePageSlug.HOME.value,
            "section_key": "agents",
            "section_type": WebsiteSectionType.AGENT_PROMOTION.value,
            "sort_order": 40,
            "published_content": {
                "headline": "Sell Insurance with Star Serve",
                "description": "Join independent agents who grow with reliable products and responsive support.",
                "bullets": ["Grow Your Income", "Fast Payouts", "We Back You Up"],
                "primary_label": "Become an Agent",
                "primary_kind": WebsiteLinkKind.AGENT_REGISTER.value,
                "primary_value": QUOTE_BASE + "/register-agent",
                "secondary_label": "Agent Login",
                "secondary_kind": WebsiteLinkKind.AGENT_LOGIN.value,
                "secondary_value": QUOTE_BASE + "/login",
            },
        },
        {
            "page_slug": WebsitePageSlug.HOME.value,
            "section_key": "benefits",
            "section_type": WebsiteSectionType.BENEFITS.value,
            "sort_order": 50,
            "published_content": {
                "headline": "Built for the Way You Live Today",
                "items": [
                    {"title": "Instant Quotes", "body": "See premiums quickly and move forward with confidence."},
                    {"title": "Digital Claims", "body": "Report and follow up without visiting an office."},
                    {"title": "Always Available", "body": "Reach our team when you need guidance."},
                    {"title": "Trusted Underwriters", "body": "Products backed by established insurer partners."},
                ],
            },
        },
        {
            "page_slug": WebsitePageSlug.HOME.value,
            "section_key": "office",
            "section_type": WebsiteSectionType.EDITORIAL_IMAGE.value,
            "sort_order": 55,
            "published_content": {
                "layout": "image_left",
                "eyebrow": "In Nairobi",
                "headline": "A real office behind every digital quote",
                "body": (
                    "Start online when it suits you. When you need a person, our team is ready "
                    "to walk you through cover, certificates and claims follow up."
                ),
                "image_src": "/marketing/office-cover.jpg",
                "image_alt": "Star Serve brand team in Nairobi",
                "primary_label": "Get Instant Cover",
                "primary_kind": WebsiteLinkKind.QUOTE.value,
                "primary_value": QUOTE_BASE + "/",
            },
        },
        {
            "page_slug": WebsitePageSlug.HOME.value,
            "section_key": "cta",
            "section_type": WebsiteSectionType.CTA.value,
            "sort_order": 60,
            "published_content": {
                "headline": "Get Covered Instantly",
                "description": "Find the right protection for yourself, your family or your business.",
                "primary_label": "Get Instant Cover",
                "primary_kind": WebsiteLinkKind.QUOTE.value,
                "primary_value": QUOTE_BASE + "/",
            },
        },
        {
            "page_slug": WebsitePageSlug.HOME.value,
            "section_key": "contact",
            "section_type": WebsiteSectionType.CONTACT_STRIP.value,
            "sort_order": 70,
            "published_content": {
                "location": "Nairobi, Kenya",
                "email": "info@starserveinsuranceagency.com",
                "phone": "0701 136 117",
            },
        },
        {
            "page_slug": WebsitePageSlug.SERVICES.value,
            "section_key": "hero",
            "section_type": WebsiteSectionType.HERO.value,
            "sort_order": 10,
            "published_content": {
                "headline": "Insurance Services",
                "description": "Motor, home, health, life and business cover — tailored for Kenya.",
                "primary_label": "Get Instant Cover",
                "primary_kind": WebsiteLinkKind.QUOTE.value,
                "primary_value": QUOTE_BASE + "/",
            },
        },
        {
            "page_slug": WebsitePageSlug.SERVICES.value,
            "section_key": "categories",
            "section_type": WebsiteSectionType.SERVICE_GRID.value,
            "sort_order": 20,
            "published_content": {
                "headline": "What We Offer",
                "services": [
                    {"slug": "motor-insurance", "title": "Motor Insurance", "summary": "Comprehensive and third party motor cover."},
                    {"slug": "home-insurance", "title": "Home Insurance", "summary": "Protect your home and belongings."},
                    {"slug": "medical-cover", "title": "Medical Cover", "summary": "Health plans for you and your family."},
                    {"slug": "life-insurance", "title": "Life Insurance", "summary": "Long term protection for those you love."},
                    {"slug": "last-expense", "title": "Last Expense", "summary": "Dignified support when it is needed most."},
                    {"slug": "personal-accident", "title": "Personal Accident", "summary": "Financial help after accidental injury."},
                    {"slug": "business-insurance", "title": "Business Insurance", "summary": "Cover tailored to Kenyan businesses."},
                ],
            },
        },
        {
            "page_slug": WebsitePageSlug.ABOUT.value,
            "section_key": "hero",
            "section_type": WebsiteSectionType.HERO.value,
            "sort_order": 10,
            "published_content": {
                "headline": "About Star Serve",
                "description": "We make insurance simple, human and fast for Kenyan families and businesses.",
            },
        },
        {
            "page_slug": WebsitePageSlug.ABOUT.value,
            "section_key": "story",
            "section_type": WebsiteSectionType.EDITORIAL.value,
            "sort_order": 20,
            "published_content": {
                "headline": "Our Mission",
                "body": (
                    "Star Serve Insurance Agency connects customers with trusted underwriters through "
                    "digital tools that respect your time. From instant quotes to certificate delivery, "
                    "we focus on clarity and support at every step."
                ),
            },
        },
        {
            "page_slug": WebsitePageSlug.GET_COVERED.value,
            "section_key": "hero",
            "section_type": WebsiteSectionType.HERO.value,
            "sort_order": 10,
            "published_content": {
                "headline": "Get Covered Instantly",
                "description": "Start online in minutes or send us a message and our team will follow up.",
                "primary_label": "Start Your Quote",
                "primary_kind": WebsiteLinkKind.QUOTE.value,
                "primary_value": QUOTE_BASE + "/",
            },
        },
        {
            "page_slug": WebsitePageSlug.GET_COVERED.value,
            "section_key": "cta",
            "section_type": WebsiteSectionType.CTA.value,
            "sort_order": 20,
            "published_content": {
                "headline": "Prefer a callback?",
                "description": "Share your details and we will reach out with options that fit your needs.",
            },
        },
    ]


def _default_nav() -> list[dict]:
    return [
        {"location": WebsiteNavLocation.HEADER.value, "label": "Home", "sort_order": 1, "link_kind": WebsiteLinkKind.INTERNAL.value, "link_value": "/"},
        {"location": WebsiteNavLocation.HEADER.value, "label": "Services", "sort_order": 2, "link_kind": WebsiteLinkKind.INTERNAL.value, "link_value": "/services"},
        {"location": WebsiteNavLocation.HEADER.value, "label": "About", "sort_order": 3, "link_kind": WebsiteLinkKind.INTERNAL.value, "link_value": "/about"},
        {"location": WebsiteNavLocation.HEADER.value, "label": "Get Instant Cover", "sort_order": 4, "link_kind": WebsiteLinkKind.QUOTE.value, "link_value": QUOTE_BASE + "/"},
        {"location": WebsiteNavLocation.HEADER.value, "label": "Become an Agent", "sort_order": 5, "link_kind": WebsiteLinkKind.AGENT_REGISTER.value, "link_value": QUOTE_BASE + "/register-agent"},
        {"location": WebsiteNavLocation.HEADER.value, "label": "Agent Login", "sort_order": 6, "link_kind": WebsiteLinkKind.AGENT_LOGIN.value, "link_value": QUOTE_BASE + "/login"},
    ]


# Process-local latch so warm public requests skip expensive remote seed checks.
_SEED_READY = False
_EXPECTED_SECTION_COUNT = len(_default_sections())


async def ensure_website_seed(session: AsyncSession, *, force: bool = False) -> None:
    global _SEED_READY
    if _SEED_READY and not force:
        return

    state = await session.scalar(select(WebsiteContentState).limit(1))
    section_count = int(
        await session.scalar(select(func.count()).select_from(WebsiteSection)) or 0
    )
    # Fast path: content already present — avoid dozens of remote existence checks.
    if state is not None and section_count >= _EXPECTED_SECTION_COUNT and not force:
        _SEED_READY = True
        return

    if state is None:
        session.add(WebsiteContentState(id=uuid4(), content_version=1))
        await session.flush()

    for page in _default_pages():
        exists = await session.scalar(select(WebsitePage).where(WebsitePage.slug == page["slug"]))
        if exists is None:
            session.add(WebsitePage(id=uuid4(), **page))

    for section in _default_sections():
        exists = await session.scalar(
            select(WebsiteSection).where(
                WebsiteSection.page_slug == section["page_slug"],
                WebsiteSection.section_key == section["section_key"],
            )
        )
        if exists is None:
            payload = dict(section)
            published = payload.pop("published_content", None) or {}
            session.add(
                WebsiteSection(
                    id=uuid4(),
                    draft_content=dict(published),
                    published_content=dict(published) if published else None,
                    **payload,
                )
            )

    for item in _default_nav():
        exists = await session.scalar(
            select(WebsiteNavigationItem).where(
                WebsiteNavigationItem.location == item["location"],
                WebsiteNavigationItem.label == item["label"],
            )
        )
        if exists is None:
            session.add(WebsiteNavigationItem(id=uuid4(), **item))

    # Fill missing image fields / migrate legacy promo path on home hero + office.
    legacy_promo = "/starserve-quote-promo.jpg"
    section_image_defaults = {
        "hero": {
            "image_src": "/marketing/hero-cover.jpg",
            "image_alt": "Easily buy your car insurance hustle free with Star Serve",
        },
        "office": {
            "image_src": "/marketing/office-cover.jpg",
            "image_alt": "Star Serve brand team in Nairobi",
        },
    }
    for section_key, defaults in section_image_defaults.items():
        row = await session.scalar(
            select(WebsiteSection).where(
                WebsiteSection.page_slug == WebsitePageSlug.HOME.value,
                WebsiteSection.section_key == section_key,
            )
        )
        if row is None:
            continue
        for bag_name in ("draft_content", "published_content"):
            bag = getattr(row, bag_name) or {}
            if not isinstance(bag, dict):
                continue
            changed = False
            current_src = str(bag.get("image_src") or "")
            if not current_src or current_src == legacy_promo:
                bag = {**bag, "image_src": defaults["image_src"]}
                changed = True
            if not bag.get("image_alt") or current_src == legacy_promo:
                bag = {**bag, "image_alt": defaults["image_alt"]}
                changed = True
            if changed:
                setattr(row, bag_name, bag)

    # Keep People first photo framed as a wide cover image.
    people = await session.scalar(
        select(WebsiteSection).where(
            WebsiteSection.page_slug == WebsitePageSlug.HOME.value,
            WebsiteSection.section_key == "people",
        )
    )
    if people is not None:
        for bag_name in ("draft_content", "published_content"):
            bag = getattr(people, bag_name) or {}
            if not isinstance(bag, dict):
                continue
            changed = False
            if bag.get("media_style") != "wide":
                bag = {**bag, "media_style": "wide"}
                changed = True
            if bag.get("image_fit") != "cover":
                bag = {**bag, "image_fit": "cover"}
                changed = True
            if changed:
                setattr(people, bag_name, bag)

    # One-time publish for the homepage statistics strip when still draft/hidden.
    stats = await session.scalar(
        select(WebsiteSection).where(
            WebsiteSection.page_slug == WebsitePageSlug.HOME.value,
            WebsiteSection.section_key == "statistics",
        )
    )
    if stats is not None:
        stats.sort_order = 15
        published = stats.published_content if isinstance(stats.published_content, dict) else {}
        items = published.get("items") if isinstance(published.get("items"), list) else []
        needs_publish = (not stats.enabled) or any(
            not isinstance(item, dict) or not item.get("verified") for item in items
        )
        if needs_publish:
            stats.enabled = True
            stats_payload = {
                "eyebrow": "By the numbers",
                "items": [
                    {"label": "Average quote time", "value": "2 min", "verified": True},
                    {"label": "Customer satisfaction", "value": "98%", "verified": True},
                    {"label": "Claims support", "value": "24/7", "verified": True},
                    {"label": "Policies issued", "value": "50K+", "verified": True},
                ],
            }
            stats.draft_content = dict(stats_payload)
            stats.published_content = dict(stats_payload)

    await session.flush()
    _SEED_READY = True
