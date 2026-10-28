"""Star Serve FastAPI application factory."""

from contextlib import asynccontextmanager
from collections.abc import AsyncIterator
import asyncio

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from redis.asyncio import from_url as redis_from_url

from app.core.config import get_settings
from app.core.database import dispose_engine
from app.core.database.dedicated import bootstrap_dedicated_databases, dispose_dedicated_engines
from app.core.exceptions.handlers import register_exception_handlers
from app.core.logging import configure_logging, get_logger
from app.core.middleware import (
    CsrfMiddleware,
    RateLimitMiddleware,
    RequestContextMiddleware,
    RequestSizeLimitMiddleware,
    SecurityHeadersMiddleware,
)
from app.api.router import api_router
from app.modules.health.router import router as health_router
from app.modules.health.router import set_redis

# Ensure reference tables are registered on Base.metadata for FK resolution
from app.modules.reference import models as _reference_models  # noqa: F401
from app.modules.system_config import models as _system_config_models  # noqa: F401
from app.modules.tenants import models as _tenant_models  # noqa: F401
from app.modules.auth import lockout_models as _lockout_models  # noqa: F401
from app.modules.commissions import models as _commission_models  # noqa: F401
from app.modules.insurer_catalog import models as _insurer_catalog_models  # noqa: F401
from app.modules.referrals import models as _referral_models  # noqa: F401
from app.modules.ussd import models as _ussd_models  # noqa: F401

logger = get_logger(__name__)


@asynccontextmanager
async def lifespan(_app: FastAPI) -> AsyncIterator[None]:
    settings = get_settings()
    configure_logging()
    redis = None
    try:
        redis = redis_from_url(settings.redis_url, decode_responses=True)
        await redis.ping()
        set_redis(redis)
        logger.info("redis_connected")
    except Exception:
        logger.warning("redis_unavailable_using_memory_fallback")
        set_redis(None)
        redis = None

    try:
        n = await bootstrap_dedicated_databases()
        if n:
            logger.info("dedicated_databases_bootstrapped", extra={"count": n})
    except Exception:
        logger.exception("dedicated_databases_bootstrap_failed")

    try:
        from app.modules.notifications.dispatcher import start_email_dispatcher

        await start_email_dispatcher(settings)
    except Exception:
        logger.exception("email_dispatcher_boot_failed")

    try:
        from app.modules.insurer_catalog.service import start_catalog_refresher

        await start_catalog_refresher()
    except Exception:
        logger.exception("insurer_catalog_refresher_boot_failed")

    yield

    from app.integrations.notifications.factory import shutdown_notification_providers
    from app.modules.insurer_catalog.service import stop_catalog_refresher
    from app.modules.notifications.dispatcher import stop_email_dispatcher

    async def _shutdown_step(name: str, awaitable) -> None:
        try:
            await asyncio.wait_for(awaitable, timeout=4.0)
        except TimeoutError:
            logger.warning("lifespan_shutdown_timed_out", extra={"step": name})
        except Exception:
            logger.exception("lifespan_shutdown_failed", extra={"step": name})

    await _shutdown_step("insurer_catalog_refresher", stop_catalog_refresher())
    await _shutdown_step("email_dispatcher", stop_email_dispatcher())
    await _shutdown_step("notification_providers", shutdown_notification_providers())
    if redis is not None:
        await _shutdown_step("redis", redis.aclose())
    await _shutdown_step("dedicated_engines", dispose_dedicated_engines())
    await _shutdown_step("engine", dispose_engine())


def _assert_production_secrets(settings) -> None:
    """Refuse to boot production with placeholder credentials."""
    if not settings.is_production:
        return
    if settings.allow_insecure_production and not settings.database_host_is_local:
        raise RuntimeError(
            "Refusing to start production: ALLOW_INSECURE_PRODUCTION is not "
            "allowed against a remote database"
        )
    if settings.allow_receipt_confirm is True and not settings.local_insecure_override:
        raise RuntimeError(
            "Refusing to start production: ALLOW_RECEIPT_CONFIRM cannot be enabled"
        )
    if settings.allow_manual_wallet_credit is True and not settings.local_insecure_override:
        raise RuntimeError(
            "Refusing to start production: ALLOW_MANUAL_WALLET_CREDIT cannot be enabled"
        )
    if settings.local_insecure_override:
        # Explicit local dual-plane docker only — placeholders stay allowed there.
        return
    insecure = []
    if "change-me" in (settings.csrf_secret or "").lower():
        insecure.append("CSRF_SECRET")
    if "change-me" in (settings.encryption_key or "").lower():
        insecure.append("ENCRYPTION_KEY")
    if "localhost" in (settings.database_url or "") or "starserve:starserve@" in (
        settings.database_url or ""
    ):
        insecure.append("DATABASE_URL")
    if (settings.jwt_algorithm or "").upper() != "RS256":
        insecure.append("JWT_ALGORITHM")
    if settings.birdview_live and not (settings.birdview_webhook_secret or "").strip():
        insecure.append("BIRDVIEW_WEBHOOK_SECRET")
    if settings.guest_quote_enabled and (
        not (settings.guest_signing_secret or "").strip()
        or "change-me" in (settings.guest_signing_secret or "").lower()
    ):
        insecure.append("GUEST_SIGNING_SECRET")
    # GUEST_TENANT_ID is optional — ensure_default_guest_agency provisions a11ce000-…
    if settings.resolved_email_provider in {"gmail", "smtp"} and not (
        settings.email_smtp_password_normalized and (settings.email_smtp_username or "").strip()
    ):
        insecure.append("EMAIL_SMTP_USERNAME|EMAIL_SMTP_PASSWORD")
    if settings.resolved_email_provider == "sendgrid" and not (
        settings.email_api_key or ""
    ).strip():
        insecure.append("EMAIL_API_KEY")
    if settings.resolved_email_provider == "ses" and not (
        settings.email_smtp_password_normalized and (settings.email_smtp_username or "").strip()
    ):
        insecure.append("EMAIL_SMTP_USERNAME|EMAIL_SMTP_PASSWORD")
    from app.core.security.provider_config import definite_integration_enabled

    if definite_integration_enabled(settings) and not (
        settings.definite_assurance_agent_code or ""
    ).strip():
        insecure.append("DEFINITE_ASSURANCE_AGENT_CODE")
    # Live BirdView: HMAC on callbackUrl + M-Pesa receipt on success. HTTPS callback
    # base is required; IP allowlist / result signatures remain optional hardenings.
    callback_base = (
        (settings.birdview_callback_base_url or settings.mpesa_callback_base_url or "")
        .strip()
        .lower()
    )
    if settings.birdview_live and callback_base and not callback_base.startswith("https://"):
        insecure.append("BIRDVIEW_CALLBACK_HTTPS")
    if insecure:
        raise RuntimeError(
            "Refusing to start production with insecure defaults: " + ", ".join(insecure)
        )


def create_app() -> FastAPI:
    settings = get_settings()
    _assert_production_secrets(settings)
    app = FastAPI(
        title=settings.app_name,
        version="1.0.0",
        docs_url="/docs" if not settings.is_production else None,
        redoc_url="/redoc" if not settings.is_production else None,
        openapi_url="/openapi.json" if not settings.is_production else None,
        lifespan=lifespan,
    )

    if settings.is_production and "*" in settings.cors_origin_list:
        raise RuntimeError("Wildcard CORS is forbidden in production")

    app.add_middleware(
        CORSMiddleware,
        allow_origins=settings.cors_origin_list,
        allow_credentials=True,
        allow_methods=["GET", "POST", "PUT", "PATCH", "DELETE", "OPTIONS"],
        allow_headers=[
            "Authorization",
            "Content-Type",
            "X-CSRF-Token",
            "X-Client-Device-Id",
            "X-Request-ID",
            "X-Job-ID",
            "X-Correlation-ID",
            "Idempotency-Key",
        ],
        expose_headers=["X-Request-ID", "X-Job-ID", "X-Correlation-ID"],
    )
    app.add_middleware(SecurityHeadersMiddleware)
    app.add_middleware(CsrfMiddleware)
    app.add_middleware(RateLimitMiddleware)
    app.add_middleware(RequestSizeLimitMiddleware)
    app.add_middleware(RequestContextMiddleware)

    hosts = [h.strip() for h in (settings.allowed_hosts or "").split(",") if h.strip()]
    if hosts and "*" not in hosts:
        from fastapi.middleware.trustedhost import TrustedHostMiddleware

        app.add_middleware(TrustedHostMiddleware, allowed_hosts=hosts)

    register_exception_handlers(app)
    app.include_router(health_router)
    app.include_router(api_router, prefix=settings.api_prefix)
    return app


app = create_app()
