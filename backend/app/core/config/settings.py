"""Star Serve application settings — secrets from env / Secret Manager only.

Never expose DATABASE_URL, JWT keys, provider passwords, or encryption keys
via API responses or Vite (VITE_*) variables.
"""

from __future__ import annotations

from functools import lru_cache
from typing import Literal
from urllib.parse import urlparse

from pydantic import Field, field_validator, model_validator
from pydantic_settings import BaseSettings, SettingsConfigDict

from app.core.postgres_provider import (
    DatabaseProvider,
    detect_provider,
    normalize_asyncpg_url,
    redact_database_url,
)


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=(".env", "../.env"),
        env_file_encoding="utf-8",
        extra="ignore",
    )

    app_name: str = "Star Serve"
    app_env: Literal["development", "staging", "production", "backup"] = "development"
    app_debug: bool = False
    # Local docker only: allow APP_ENV=production against starserve_live + non-prod secrets.
    # Never set true on Cloud Run / real production.
    allow_insecure_production: bool = False
    api_prefix: str = "/api/v1"

    cors_origins: str = "http://localhost:5173,http://127.0.0.1:5173"

    # --- Database (one DSN per process / Cloud Run revision) ---
    # Prefer env-specific URLs below; APP_ENV selects which one is active.
    database_url: str = "postgresql+asyncpg://starserve:starserve@localhost:5432/starserve"
    database_url_development: str | None = None
    database_url_staging: str | None = None
    database_url_production: str | None = None
    database_url_backup: str | None = None

    # local | supabase | cloud_sql | generic — auto-detected from URL when "auto"
    db_provider: str = "auto"
    supabase_project_ref: str = "wbasegyvtchdmkfkyoei"
    # REST API — backend only. Never expose service_role via API or Vite.
    supabase_url: str = "https://wbasegyvtchdmkfkyoei.supabase.co"
    supabase_anon_key: str = ""
    supabase_service_role_key: str = ""
    database_schema: str = "public"
    # Keep small on Cloud Run when using Supabase/Cloud SQL transaction pooler
    db_pool_size: int = 5
    db_max_overflow: int = 10
    db_pool_timeout: int = 30
    db_command_timeout: int = 30
    db_ssl_mode: str = "prefer"
    # Force NullPool (recommended with PgBouncer transaction mode / high maxScale)
    db_null_pool: bool = False

    redis_url: str = "redis://localhost:6379/0"

    jwt_algorithm: str = "RS256"
    jwt_issuer: str = "starserve"
    jwt_access_token_minutes: int = 15
    jwt_refresh_token_days: int = 14
    jwt_private_key_path: str = "secrets/dev_jwt_private.pem"
    jwt_public_key_path: str = "secrets/dev_jwt_public.pem"
    jwt_private_key: str | None = None
    jwt_public_key: str | None = None

    password_hasher: str = "argon2"
    login_max_attempts: int = 5
    login_lockout_minutes: int = 15
    rate_limit_default: str = "120/minute"
    csrf_secret: str = Field(default="change-me-csrf-dev-only")
    cookie_secure: bool = False
    cookie_samesite: Literal["lax", "strict", "none"] = "lax"
    cookie_domain: str | None = None

    encryption_key: str = "change-me-32-byte-encryption-key!!"
    # Dedicated HMAC for guest quote JWTs. Must not be derived from ENCRYPTION_KEY.
    guest_signing_secret: str = ""
    # Hosts permitted in dedicated-tenant DSNs (comma-separated). Empty refuses
    # dedicated mode in production; localhost is allowed only outside production.
    dedicated_dsn_hosts: str = ""
    trust_x_forwarded_for: bool = False
    # How many rightmost XFF hops belong to our platform (Cloud Run GFE, SPA
    # nginx, …). Used only by end_user_ip() for guest session binding — never
    # for webhook allowlists (those keep the non-spoofable rightmost hop).
    # Direct Cloud Run: 1. SPA nginx → API Cloud Run: 2.
    trusted_proxy_hops: int = 1
    allowed_hosts: str = ""
    # None = allowed outside production; must be explicit true in production.
    allow_manual_wallet_credit: bool | None = None
    # Typed M-Pesa receipt confirm (no provider verify). Off in production unless explicit.
    allow_receipt_confirm: bool | None = None
    certificate_download_hosts: str = (
        "definiteassurance.com,blob.core.windows.net,azureedge.net"
    )
    # Empty = any public https host. Set to restrict customer/user avatars.
    avatar_url_hosts: str = ""

    definite_assurance_base_url: str = "https://uat.definiteassurance.com/api/v1"
    definite_assurance_username: str = ""
    definite_assurance_password: str = ""
    definite_assurance_agent_code: str = ""
    # UAT: Definite accepts AmountPaid=1 to approve the note before generateCertificate
    definite_assurance_test_amount_paid: float = 1.0
    definite_assurance_test_phone: str = "254700000001"
    # None = auto (enforce on LIVE only; soft-check on UAT/dev)
    definite_assurance_enforce_double_insurance: bool | None = None
    definite_assurance_timeout_seconds: int = 60
    # newProposal normally answers in 2–12s; a stalled call is retried once instead of
    # holding the customer for the full default timeout.
    definite_assurance_proposal_timeout_seconds: int = 20
    # Quote catalog is served from our DB; Definite is re-read in the background
    # once the stored copy is older than this.
    insurer_catalog_refresh_seconds: int = 1800
    insurer_catalog_background_refresh: bool = True

    # Payment providers (Phase 5) — never expose to frontend / Vite
    mpesa_consumer_key: str = ""
    mpesa_consumer_secret: str = ""
    mpesa_shortcode: str = ""
    mpesa_passkey: str = ""
    mpesa_webhook_secret: str = ""
    mpesa_callback_base_url: str = "http://localhost:8000"
    mpesa_daraja_base_url: str = "https://api.safaricom.co.ke"
    mpesa_live: bool = True
    mpesa_timeout_seconds: int = 30
    # Optional Daraja source IPs / CIDRs. Empty = checkout binding only.
    mpesa_callback_allowed_ips: str = ""

    # BirdView STK (alternate M-Pesa rail for certificate premiums)
    birdview_stk_url: str = (
        "https://payments.birdviewinsurance.com/mobile-payments/stk-push"
    )
    # Used when the branded host fails DNS (CNAME SERVFAIL on some ISPs).
    birdview_stk_fallback_url: str = (
        "https://payments-ewrv.onrender.com/mobile-payments/stk-push"
    )
    birdview_api_key: str = ""
    birdview_webhook_secret: str = ""
    # Callback URL possession alone must not be able to assert "paid". Configure at
    # least one of these in production: the provider's source IPs (CIDRs allowed),
    # or a result signature the provider computes over the callback outcome.
    birdview_callback_allowed_ips: str = ""
    birdview_result_signature_required: bool = False
    # Public HTTPS base used as callbackUrl (falls back to mpesa_callback_base_url)
    birdview_callback_base_url: str = ""
    birdview_timeout_seconds: int = 30
    # When False, initiate stays local PENDING (no outbound STK) for offline/dev
    birdview_live: bool = False
    # Dev/UAT only: charge this KES on STK / Definite AmountPaid while policy premium
    # stays authoritative on the payment row. Forbidden in production.
    # Unset in non-production → defaults to 1.00 KES (see payments.dev_charge).
    birdview_test_amount: float | None = None

    # Notification providers (Phase 6) — never expose to frontend / Vite
    # TextSMS (sms.textsms.co.ke) — API key + partner ID from Secret Manager.
    sms_api_key: str = ""
    sms_partner_id: str = ""
    sms_api_url: str = "https://sms.textsms.co.ke/api/services/sendsms/"
    sms_sender_id: str = "STARSERVE"
    sms_timeout_seconds: float = 8.0
    # True = call the SMS API on the request path (tests / emergency only)
    sms_deliver_inline: bool = False
    whatsapp_api_token: str = ""

    # Email: stub | gmail | smtp | ses | sendgrid | auto
    # auto = Gmail/SMTP when a password is set, otherwise stub (tests/dev).
    email_provider: str = "auto"
    email_api_key: str = ""  # SendGrid / ESP API key — not the Gmail password
    email_from_name: str = "Star Serve"
    email_from_address: str = "noreply@starserve.local"
    email_reply_to: str = ""
    email_support_address: str = "hello@starserve.local"
    email_support_phone: str = ""
    email_support_hours: str = "Monday – Friday, 8:00 AM – 5:00 PM EAT"
    email_legal_line: str = "Star Serve Insurance Agency · Nairobi, Kenya"
    email_app_url: str = "http://localhost:5173"
    email_logo_url: str = ""
    # Gmail: use an App Password, not the Google account password.
    email_smtp_host: str = "smtp.gmail.com"
    email_smtp_port: int = 587
    email_smtp_username: str = ""
    email_smtp_password: str = ""
    email_smtp_use_tls: bool = True
    email_smtp_use_ssl: bool = False
    email_smtp_timeout_seconds: float = 20.0
    email_ses_region: str = "eu-west-1"
    # Throughput — None = provider preset (Gmail is conservative on purpose)
    email_rate_per_second: float | None = None
    email_max_connections: int | None = None
    email_send_concurrency: int | None = None
    email_worker_enabled: bool = True
    email_worker_poll_seconds: float = 1.0
    email_worker_batch_size: int = 50
    # True = SMTP on the request path (tests / emergency only)
    email_deliver_inline: bool = False

    log_level: str = "INFO"
    log_json: bool = True
    sentry_dsn: str | None = None

    access_cookie_name: str = "ss_access"
    refresh_cookie_name: str = "ss_refresh"
    csrf_cookie_name: str = "ss_csrf"
    csrf_header_name: str = "X-CSRF-Token"

    # Guest welcome-screen quotes (OWASP-style capability cookie; not public issuance)
    guest_quote_enabled: bool = True
    guest_cookie_name: str = "ss_guest"
    guest_session_minutes: int = 45
    # Caps *new* guest session mints per IP/hour. Reuse/refresh of a valid
    # cookie does not count. Keep high enough for SPA remounts + agency switches.
    # (Per-route guest limits live in guest_session.py — not a shared API bucket.)
    guest_rate_limit_per_hour: int = 600
    guest_mint_limit_per_hour: int = 60
    # Agency tenant that owns guest-created customers/proposals/policies.
    # Empty = first active non-platform insurance agency (dev convenience only).
    guest_tenant_id: str | None = None

    # USSD channel (provider callback + admin simulator)
    ussd_enabled: bool = True
    ussd_allow_unauthenticated: bool = False
    ussd_hash_pepper: str = ""
    ussd_default_service_code: str = "*652*6#"

    max_request_body_bytes: int = 1_048_576  # 1 MiB

    # Object storage — local data/ for development; GCS on Cloud Run.
    # Postgres stores relative keys only; the bucket stays non-public.
    storage_backend: str = "local"  # local | gcs
    gcs_bucket: str = "star_serve"
    # Optional env prefix inside the bucket (staging | production | backup).
    gcs_prefix: str = ""

    # Local certificate PDFs — never expose absolute paths via API
    certificate_storage_dir: str = "data/certificates"
    # Claim / certificate PDFs attached to outbound mail (queue cannot store blobs)
    email_pdf_storage_dir: str = "data/email-pdfs"

    # Claims documents and signed integration callbacks
    claims_document_dir: str = "data/claims/documents"
    claims_document_max_bytes: int = 8_388_608
    # Staff profile photo upload (POST /auth/me/avatar)
    avatar_max_bytes: int = 10_485_760  # 10 MiB
    claims_webhook_hmac_secret: str = ""
    claims_webhook_timestamp_window_seconds: int = 300

    @field_validator("cors_origins", mode="before")
    @classmethod
    def _strip_origins(cls, value: object) -> object:
        return value

    @model_validator(mode="after")
    def _select_env_database_url(self) -> Settings:
        """Pick isolated DSN for APP_ENV when env-specific URLs are configured."""
        env_map = {
            "development": self.database_url_development,
            "staging": self.database_url_staging,
            "production": self.database_url_production,
            "backup": self.database_url_backup,
        }
        chosen = env_map.get(self.app_env)
        if chosen:
            object.__setattr__(self, "database_url", normalize_asyncpg_url(chosen))
        else:
            object.__setattr__(self, "database_url", normalize_asyncpg_url(self.database_url))
        if self.cookie_samesite == "none" and not (self.cookie_secure or self.is_production):
            raise ValueError("COOKIE_SAMESITE=none requires COOKIE_SECURE=true")
        return self

    @property
    def cors_origin_list(self) -> list[str]:
        return [o.strip() for o in self.cors_origins.split(",") if o.strip()]

    @property
    def is_production(self) -> bool:
        return self.app_env == "production"

    @property
    def definite_is_uat(self) -> bool:
        """True when talking to Definite UAT — test AmountPaid=1 is only safe there."""
        return "uat" in (self.definite_assurance_base_url or "").lower()

    @property
    def database_host(self) -> str:
        raw = (self.database_url or "").replace("postgresql+asyncpg://", "postgresql://", 1)
        return (urlparse(raw).hostname or "").lower()

    @property
    def database_host_is_local(self) -> bool:
        return self.database_host in {
            "localhost",
            "127.0.0.1",
            "::1",
            "postgres",
            "db",
            "starserve",
            "starserve-db",
        }

    @property
    def local_insecure_override(self) -> bool:
        """True only for explicit local dual-plane docker — never Cloud Run."""
        return bool(self.allow_insecure_production and self.database_host_is_local)

    @property
    def jwt_audience(self) -> str:
        return f"{self.jwt_issuer}:{self.app_env}"

    @property
    def manual_wallet_credit_allowed(self) -> bool:
        if self.is_production and not self.local_insecure_override:
            return False
        if self.allow_manual_wallet_credit is not None:
            return self.allow_manual_wallet_credit
        return not self.is_production

    @property
    def receipt_confirm_allowed(self) -> bool:
        if self.is_production and not self.local_insecure_override:
            return False
        if self.allow_receipt_confirm is not None:
            return self.allow_receipt_confirm
        return not self.is_production

    @property
    def data_plane(self) -> Literal["staging", "live", "backup"]:
        """Product data plane — never share one DB across planes.

        development/staging → staging (non-production data)
        production → live (customer data)
        backup → backup (restored / archival copy of live)
        Isolation is physical (separate DATABASE_URL / deployment), not a row flag.
        """
        if self.app_env == "production":
            return "live"
        if self.app_env == "backup":
            return "backup"
        return "staging"

    @property
    def resolved_db_provider(self) -> DatabaseProvider:
        explicit = None if self.db_provider.lower() == "auto" else self.db_provider
        return detect_provider(self.database_url, explicit)

    @property
    def database_url_redacted(self) -> str:
        return redact_database_url(self.database_url)

    @property
    def email_smtp_password_normalized(self) -> str:
        """Gmail App Passwords are often copied with spaces — strip them."""
        return (self.email_smtp_password or "").replace(" ", "")

    @property
    def resolved_email_provider(self) -> str:
        raw = (self.email_provider or "auto").strip().lower()
        allowed = {"auto", "stub", "gmail", "smtp", "ses", "sendgrid"}
        if raw not in allowed:
            return "stub"
        if raw != "auto":
            return raw
        if self.email_smtp_password_normalized:
            host = (self.email_smtp_host or "smtp.gmail.com").lower()
            if "gmail" in host or "google" in host:
                return "gmail"
            return "smtp"
        return "stub"

    @property
    def email_async_delivery(self) -> bool:
        """SMTP/HTTP must not run on the request thread except explicit inline mode."""
        if self.email_deliver_inline:
            return False
        return self.resolved_email_provider != "stub"

    @property
    def email_dispatcher_enabled(self) -> bool:
        return bool(self.email_worker_enabled) and self.resolved_email_provider != "stub"

    @property
    def sms_live(self) -> bool:
        return bool(
            (self.sms_api_key or "").strip() and (self.sms_partner_id or "").strip()
        )

    @property
    def sms_async_delivery(self) -> bool:
        return self.sms_live and not self.sms_deliver_inline and bool(self.email_worker_enabled)

    @property
    def dispatcher_channels(self) -> tuple[str, ...]:
        """Channels drained by the background notification dispatcher."""
        channels: list[str] = []
        if self.email_dispatcher_enabled:
            channels.append("EMAIL")
        if self.sms_async_delivery:
            channels.append("SMS")
        return tuple(channels)

    @property
    def email_rate_limit_per_second(self) -> float:
        if self.email_rate_per_second is not None:
            return max(float(self.email_rate_per_second), 0.05)
        kind = self.resolved_email_provider
        if kind == "gmail":
            return 1.0
        if kind == "ses":
            return 14.0
        if kind == "sendgrid":
            return 40.0
        return 5.0

    @property
    def email_pool_size(self) -> int:
        if self.email_max_connections is not None:
            return max(int(self.email_max_connections), 1)
        kind = self.resolved_email_provider
        if kind == "gmail":
            return 2
        if kind == "sendgrid":
            return 8
        return 4

    @property
    def email_inflight(self) -> int:
        if self.email_send_concurrency is not None:
            return max(int(self.email_send_concurrency), 1)
        return max(self.email_pool_size, 4)


@lru_cache
def get_settings() -> Settings:
    return Settings()
