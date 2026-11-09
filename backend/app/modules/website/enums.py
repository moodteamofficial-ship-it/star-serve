"""Public website CMS enumerations."""

from enum import StrEnum


class WebsitePageSlug(StrEnum):
    HOME = "home"
    SERVICES = "services"
    ABOUT = "about"
    GET_COVERED = "get-covered"


class WebsiteSectionType(StrEnum):
    HERO = "hero"
    SERVICE_GRID = "service_grid"
    STATISTICS = "statistics"
    PARTNER_SHOWCASE = "partner_showcase"
    AGENT_PROMOTION = "agent_promotion"
    BENEFITS = "benefits"
    CTA = "cta"
    EDITORIAL = "editorial"
    EDITORIAL_IMAGE = "editorial_image"
    PROMO_CAROUSEL = "promo_carousel"
    STORY_GRID = "story_grid"
    FAQ = "faq"
    CONTACT_STRIP = "contact_strip"


class WebsiteNavLocation(StrEnum):
    HEADER = "header"
    FOOTER = "footer"


class WebsiteLinkKind(StrEnum):
    INTERNAL = "internal"
    QUOTE = "quote"
    QUOTE_PRODUCT = "quote_product"
    AGENT_REGISTER = "agent_register"
    AGENT_LOGIN = "agent_login"
    EXTERNAL = "external"
    PHONE = "phone"
    EMAIL = "email"


class WebsiteEnquiryStatus(StrEnum):
    NEW = "NEW"
    REVIEWED = "REVIEWED"
    CLOSED = "CLOSED"
