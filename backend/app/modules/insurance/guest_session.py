"""Guest quote capability sessions (welcome screen only).

Security model (aligned with OWASP ASVS / capability tokens):
- Minted only when Origin is on the configured allowlist (trusted SPA).
- Opaque session id stored in Redis; browser holds an HttpOnly cookie (not localStorage).
- CSRF double-submit required on mutations when the guest cookie is present.
- Device id bound to the session (primary); end-user IP hash is bound for
  rate limits and refreshed when the device still matches (CGNAT / Cloud Run
  multi-hop edges). Resource ids (customer/policy) are allowlisted per session
  so guests cannot enumerate peer records in the tenant.
- Short TTL; strict rate limit on mint and guest issuance paths.
"""

from __future__ import annotations

import hashlib
import hmac
import json
import secrets
import time
from datetime import UTC, datetime, timedelta
from typing import Any
from urllib.parse import urlsplit
from uuid import UUID, uuid4

import jwt
from jwt.exceptions import InvalidTokenError as JWTError
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from starlette.requests import Request
from starlette.responses import Response

from app.core.config import get_settings
from app.core.database.enums import DatabaseMode, TenantStatus, TenantType
from app.core.database.redis_client import get_redis_client, redis_fail_closed
from app.core.database.rls import set_rls_context
from app.core.exceptions import (
    AuthenticationError,
    AuthorizationError,
    SystemUnavailableError,
    ValidationAppError,
)
from app.core.security.guest_capabilities import GuestContext
from app.core.security.request import end_user_ip as resolved_client_ip
from app.modules.tenants.models import Tenant

_MEMORY_SESSIONS: dict[str, dict[str, Any]] = {}
_MEMORY_RATE: dict[str, tuple[int, float]] = {}


def _guest_signing_key() -> bytes:
    """HMAC key for guest JWTs — never derived from ENCRYPTION_KEY.

    ENCRYPTION_KEY unwraps dedicated DSNs. Reusing it here meant a guest-token
    leak (or a guest-secret rotation) was also a database-secret leak.
    """
    settings = get_settings()
    material = (settings.guest_signing_secret or "").strip()
    if not material or "change-me" in material.lower():
        if settings.is_production and not settings.allow_insecure_production:
            raise AuthenticationError("Guest signing material is not configured")
        material = (settings.csrf_secret or "").strip()
    if not material:
        raise AuthenticationError("Guest signing material is not configured")
    return hashlib.sha256(f"guest-quote:v3:{material}".encode()).digest()


def _guest_jwt_claims(
    *,
    jti: str,
    tenant_id: str,
    iat: int,
    exp: int,
    device_hash: str,
    ip_hash: str,
) -> dict[str, Any]:
    settings = get_settings()
    return {
        "typ": "guest",
        "jti": jti,
        "tid": tenant_id,
        "dh": device_hash,
        "ih": ip_hash,
        "iss": settings.jwt_issuer,
        "aud": settings.jwt_audience,
        "iat": iat,
        "exp": exp,
    }


def _decode_guest_token(token: str) -> dict[str, Any]:
    settings = get_settings()
    return jwt.decode(
        token,
        _guest_signing_key(),
        algorithms=["HS256"],
        issuer=settings.jwt_issuer,
        audience=settings.jwt_audience,
        options={"require": ["exp", "jti", "iss", "aud"]},
    )


def _guest_device_id(request: Request) -> str:
    device = (request.headers.get("x-client-device-id") or "").strip()[:128]
    if device:
        return device
    if get_settings().is_production:
        raise AuthenticationError("Guest session device id is required")
    return "unknown"


def _hash_bind(value: str) -> str:
    return hashlib.sha256(value.encode()).hexdigest()[:32]


def client_ip(request: Request) -> str:
    return resolved_client_ip(request) or "unknown"


_TRUSTED_FETCH_SITES = frozenset({"same-origin", "same-site"})


def _canonical_origin(value: str) -> str:
    """Return scheme://host[:port] or empty. Rejects null, credentials, and junk."""
    raw = (value or "").strip()
    if not raw or raw.lower() == "null":
        return ""
    parts = urlsplit(raw)
    if parts.scheme not in {"http", "https"}:
        return ""
    if parts.username or parts.password:
        return ""
    host = (parts.hostname or "").lower()
    if not host or host == "null" or "\\" in host:
        return ""
    scheme = parts.scheme.lower()
    try:
        port = parts.port
    except ValueError:
        return ""
    if ":" in host:
        host = f"[{host}]"
    if port is None or (scheme == "http" and port == 80) or (scheme == "https" and port == 443):
        return f"{scheme}://{host}"
    return f"{scheme}://{host}:{port}"


def _allowed_origins() -> set[str]:
    return {
        origin
        for origin in (_canonical_origin(item) for item in get_settings().cors_origin_list)
        if origin
    }


def require_trusted_origin(request: Request) -> str:
    """Guest APIs must come from a CORS-allowlisted browser origin.

    Cross-origin fetch always sends Origin. Same-origin GETs (Vite proxy, same
    host) often omit it — recover only when Fetch Metadata says the request is
    not cross-site *and* Referer maps to the same allowlist. Origin: null,
    cross-site, and missing metadata stay rejected.
    """
    allowed = _allowed_origins()
    declared = _canonical_origin(request.headers.get("origin") or "")
    if declared:
        if declared not in allowed:
            raise AuthorizationError("Request origin is not allowed for guest quotes")
        return declared

    site = (request.headers.get("sec-fetch-site") or "").strip().lower()
    if site not in _TRUSTED_FETCH_SITES:
        raise AuthorizationError("Trusted guest origin is required")

    referer_origin = _canonical_origin(request.headers.get("referer") or "")
    if not referer_origin or referer_origin not in allowed:
        raise AuthorizationError("Trusted guest origin is required")
    return referer_origin


async def _arm_redis_window(redis: Any, key: str, count: int, window: int) -> None:
    """Fixed window: set TTL on first hit, never refresh it on later traffic.

    Refreshing expire() on every incr keeps a busy key alive forever, so a
    legitimate SPA that already crossed the cap could never recover.
    """
    ttl = int(await redis.ttl(key))
    if count == 1 or ttl < 0:
        await redis.expire(key, window)


async def _counter_incr(key: str, *, window: int = 3600) -> int:
    redis = get_redis_client()
    if redis is not None:
        try:
            count = int(await redis.incr(key))
            await _arm_redis_window(redis, key, count, window)
            return count
        except Exception:
            if redis_fail_closed():
                raise ValidationAppError("Guest session store is temporarily unavailable")
    elif redis_fail_closed():
        raise ValidationAppError("Guest session store is temporarily unavailable")
    now = time.time()
    count, reset = _MEMORY_RATE.get(key, (0, now + window))
    if now > reset:
        count, reset = 0, now + window
    count += 1
    _MEMORY_RATE[key] = (count, reset)
    return count


async def _counter_decr(key: str) -> None:
    redis = get_redis_client()
    if redis is not None:
        try:
            await redis.decr(key)
            return
        except Exception:
            if redis_fail_closed():
                return
    elif redis_fail_closed():
        return
    count, reset = _MEMORY_RATE.get(key, (0, 0))
    _MEMORY_RATE[key] = (max(0, count - 1), reset)


async def _rate_allow(key: str, *, limit: int, window: int = 3600) -> bool:
    redis = get_redis_client()
    if redis is not None:
        try:
            count = int(await redis.incr(key))
            await _arm_redis_window(redis, key, count, window)
            return count <= limit
        except Exception:
            if redis_fail_closed():
                return False
    elif redis_fail_closed():
        return False
    now = time.time()
    count, reset = _MEMORY_RATE.get(key, (0, now + window))
    if now > reset:
        count, reset = 0, now + window
    count += 1
    _MEMORY_RATE[key] = (count, reset)
    return count <= limit


# Stable id so guest quotes land in one agency even before seed_phase1 agencies exist.
DEFAULT_GUEST_AGENCY_ID = UUID("a11ce000-5e12-4000-8000-00000000c0de")
DEFAULT_GUEST_AGENCY_NAME = "Star Serve Direct"


def _guest_tenant_filter():
    return (
        Tenant.is_platform.is_(False),
        Tenant.status == TenantStatus.ACTIVE.value,
        Tenant.tenant_type.in_(
            (
                TenantType.INSURANCE_AGENCY.value,
                TenantType.BROKER.value,
            )
        ),
    )


async def ensure_default_guest_agency(db: AsyncSession) -> UUID:
    """Create the shared guest agency when the DB has no selectable agencies yet."""
    existing = await db.scalar(
        select(Tenant.id).where(Tenant.id == DEFAULT_GUEST_AGENCY_ID)
    )
    if existing is not None:
        return existing

    by_name = await db.scalar(
        select(Tenant.id)
        .where(
            Tenant.trading_name == DEFAULT_GUEST_AGENCY_NAME,
            Tenant.is_platform.is_(False),
        )
        .limit(1)
    )
    if by_name is not None:
        return by_name

    tenant = Tenant(
        id=DEFAULT_GUEST_AGENCY_ID,
        legal_name="Star Serve Direct Limited",
        trading_name=DEFAULT_GUEST_AGENCY_NAME,
        tenant_type=TenantType.INSURANCE_AGENCY.value,
        status=TenantStatus.ACTIVE.value,
        database_mode=DatabaseMode.SHARED_DATABASE.value,
        configuration={"guest_quotes": True, "auto_provisioned": True},
        branding={},
        is_platform=False,
        email="guest-quotes@starserve.local",
    )
    db.add(tenant)
    await db.flush()
    await ensure_tenant_issuance_branch(db, tenant.id)
    return tenant.id


async def ensure_tenant_issuance_branch(db: AsyncSession, tenant_id: UUID) -> UUID:
    """Guarantee a real branch exists for guest-owned records. Never NULL."""
    from app.core.security.branch_scope import first_active_tenant_branch_id
    from app.modules.tenants.models import Branch

    existing = await first_active_tenant_branch_id(db, tenant_id)
    if existing is not None:
        return existing
    settings = get_settings()
    if settings.is_production and not settings.allow_insecure_production:
        if tenant_id != DEFAULT_GUEST_AGENCY_ID:
            raise ValidationAppError("Agency has no branch for guest quotes")
    branch = Branch(
        tenant_id=tenant_id,
        name="Direct",
        code="DIRECT",
        status="ACTIVE",
    )
    db.add(branch)
    await db.flush()
    return branch.id


async def list_guest_tenants(db: AsyncSession) -> list[dict[str, str]]:
    """Public-safe agency list for the welcome-screen tenant picker."""
    settings = get_settings()
    if settings.guest_tenant_id:
        try:
            locked = UUID(str(settings.guest_tenant_id).strip())
        except ValueError as exc:
            raise ValidationAppError("GUEST_TENANT_ID is not a valid UUID") from exc
        row = await db.scalar(select(Tenant).where(Tenant.id == locked))
        if row is None or row.is_platform or row.status != TenantStatus.ACTIVE.value:
            raise ValidationAppError("Configured guest tenant is not available")
        return [
            {
                "id": str(row.id),
                "name": row.trading_name or row.legal_name,
                "tenant_type": row.tenant_type,
            }
        ]

    rows = list(
        (
            await db.scalars(
                select(Tenant)
                .where(*_guest_tenant_filter())
                .order_by(Tenant.created_at.asc(), Tenant.id.asc())
            )
        ).all()
    )
    # Listing is a GET. Creating an agency here would let anyone mint a tenant
    # just by opening the welcome screen. Provisioning stays on mint/resolve.
    return [
        {
            "id": str(row.id),
            "name": row.trading_name or row.legal_name,
            "tenant_type": row.tenant_type,
        }
        for row in rows
    ]


async def resolve_guest_tenant_id(
    db: AsyncSession,
    preferred: UUID | None = None,
) -> UUID:
    """Resolve the agency that owns guest-created quotes."""
    settings = get_settings()
    if settings.guest_tenant_id:
        try:
            locked = UUID(str(settings.guest_tenant_id).strip())
        except ValueError as exc:
            raise ValidationAppError("GUEST_TENANT_ID is not a valid UUID") from exc
        if preferred is not None and preferred != locked:
            raise ValidationAppError("Selected agency is not available for guest quotes")
        return locked

    choices = await list_guest_tenants(db)
    if not choices:
        if settings.guest_tenant_id:
            raise ValidationAppError("No agency is available for guest quotes")
        if settings.is_production and not settings.allow_insecure_production:
            raise ValidationAppError("No agency is available for guest quotes")
        await ensure_default_guest_agency(db)
        choices = await list_guest_tenants(db)
    if not choices:
        raise ValidationAppError("No agency is available for guest quotes")

    if preferred is not None:
        preferred_s = str(preferred)
        if not any(item["id"] == preferred_s for item in choices):
            raise ValidationAppError("Selected agency is not available for guest quotes")
        return preferred

    return UUID(choices[0]["id"])


async def guest_fnol_tenant_ids(db: AsyncSession, selected: UUID) -> list[UUID]:
    """Tenants a welcome-screen claim may prove identity against.

    Staff often issue on the platform tenant while the picker only lists
    agencies. When the guest selected the only agency — or Star Serve Direct —
    also search that platform tenant so a paid staff policy can be matched.
    Never adds a peer agency.
    """
    ids = [selected]
    choices = await list_guest_tenants(db)
    only_agency = len(choices) == 1 and choices[0]["id"] == str(selected)
    if only_agency or selected == DEFAULT_GUEST_AGENCY_ID:
        platform = await db.scalar(
            select(Tenant.id).where(
                Tenant.is_platform.is_(True),
                Tenant.status == TenantStatus.ACTIVE.value,
            )
        )
        if platform is not None and platform not in ids:
            ids.append(platform)
    return ids


async def bind_guest_fnol_tenant(request: Request, tenant_id: UUID) -> None:
    """Park the session on the matched policy's tenant so later reads stay consistent."""
    jti = getattr(request.state, "guest_jti", None)
    stored = getattr(request.state, "guest_session", None)
    guest: GuestContext | None = getattr(request.state, "guest_context", None)
    if not jti or not isinstance(stored, dict):
        return
    stored["tenant_id"] = str(tenant_id)
    await _update_session(jti, stored)
    request.state.guest_session = stored
    if guest is not None:
        guest.tenant_id = tenant_id
        guest.bind()


def _session_key(jti: str) -> str:
    return f"guest:sess:{jti}"


async def _save_session(jti: str, payload: dict[str, Any], ttl: int) -> None:
    redis = get_redis_client()
    raw = json.dumps(payload)
    if redis is not None:
        try:
            await redis.setex(_session_key(jti), ttl, raw)
            return
        except Exception as exc:
            if redis_fail_closed():
                raise ValidationAppError(
                    "Guest session store is temporarily unavailable"
                ) from exc
    elif redis_fail_closed():
        raise ValidationAppError("Guest session store is temporarily unavailable")
    payload = {**payload, "_expires": time.time() + ttl}
    _MEMORY_SESSIONS[jti] = payload


async def _load_session(jti: str) -> dict[str, Any] | None:
    redis = get_redis_client()
    if redis is not None:
        try:
            raw = await redis.get(_session_key(jti))
            if raw:
                return json.loads(raw)
            if redis_fail_closed():
                return None
        except Exception as exc:
            if redis_fail_closed():
                raise AuthenticationError(
                    "Guest session store is temporarily unavailable"
                ) from exc
    elif redis_fail_closed():
        raise AuthenticationError("Guest session store is temporarily unavailable")
    payload = _MEMORY_SESSIONS.get(jti)
    if not payload:
        return None
    if float(payload.get("_expires", 0)) < time.time():
        _MEMORY_SESSIONS.pop(jti, None)
        return None
    return payload


async def _update_session(jti: str, payload: dict[str, Any]) -> None:
    settings = get_settings()
    ttl = max(60, settings.guest_session_minutes * 60)
    await _save_session(jti, payload, ttl)


def _session_from_jwt(payload: dict[str, Any]) -> dict[str, Any] | None:
    """Rebuild guest allowlists when Redis/memory missed (Cloud Run scale-out)."""
    jti = str(payload.get("jti") or "")
    tenant_id = str(payload.get("tid") or "")
    device_hash = str(payload.get("dh") or "")
    ip_hash = str(payload.get("ih") or "")
    if not jti or not tenant_id or not device_hash or not ip_hash:
        return None
    return {
        "jti": jti,
        "tenant_id": tenant_id,
        "device_hash": device_hash,
        "ip_hash": ip_hash,
        "customers": [],
        "policies": [],
        "from_jwt": True,
    }


async def _hydrate_guest_bindings(
    db: AsyncSession, session_id: UUID, stored: dict[str, Any]
) -> None:
    from app.modules.customers.models import Customer
    from app.modules.policies.models import Policy

    customer_ids = list(
        (
            await db.scalars(
                select(Customer.id).where(
                    Customer.guest_session_id == session_id,
                    Customer.deleted_at.is_(None),
                )
            )
        ).all()
    )
    stored["customers"] = [str(cid) for cid in customer_ids]
    if not customer_ids:
        stored.setdefault("policies", [])
        return
    policy_ids = list(
        (await db.scalars(select(Policy.id).where(Policy.customer_id.in_(customer_ids)))).all()
    )
    stored["policies"] = [str(pid) for pid in policy_ids]


def ensure_csrf_cookie(
    request: Request,
    response: Response,
    *,
    max_age: int | None = None,
) -> str:
    """Issue or refresh the readable double-submit CSRF cookie (never HttpOnly)."""
    settings = get_settings()
    ttl = max_age if max_age is not None else max(60, settings.guest_session_minutes * 60)
    token = request.cookies.get(settings.csrf_cookie_name) or secrets.token_urlsafe(32)
    response.set_cookie(
        settings.csrf_cookie_name,
        token,
        httponly=False,
        secure=settings.cookie_secure or settings.is_production,
        samesite=settings.cookie_samesite,
        domain=settings.cookie_domain or None,
        path="/",
        max_age=ttl,
    )
    return token


def _set_guest_cookies(
    request: Request,
    response: Response,
    *,
    token: str,
    ttl: int,
) -> None:
    settings = get_settings()
    common = {
        "secure": settings.cookie_secure or settings.is_production,
        "samesite": settings.cookie_samesite,
        "domain": settings.cookie_domain or None,
        "path": "/",
        "max_age": ttl,
    }
    response.set_cookie(
        settings.guest_cookie_name,
        token,
        httponly=True,
        **common,
    )
    # Keep CSRF TTL aligned with the guest capability cookie.
    ensure_csrf_cookie(request, response, max_age=ttl)


async def _try_reuse_guest_session(
    request: Request,
    *,
    response: Response,
    resolved_tenant_id: UUID,
    device: str,
) -> dict[str, Any] | None:
    """Return a refreshed session when the caller already holds a valid cookie."""
    settings = get_settings()
    token = request.cookies.get(settings.guest_cookie_name)
    if not token:
        return None

    try:
        payload = _decode_guest_token(token)
    except JWTError:
        return None

    if payload.get("typ") != "guest":
        return None

    jti = str(payload.get("jti") or "")
    stored = await _load_session(jti)
    if not stored:
        stored = _session_from_jwt(payload)
        if stored is None:
            return None
    if str(stored.get("tenant_id")) != str(resolved_tenant_id):
        return None
    if not hmac.compare_digest(stored.get("device_hash", ""), _hash_bind(device)):
        return None
    ip = client_ip(request)
    if not hmac.compare_digest(stored.get("ip_hash", ""), _hash_bind(ip)):
        return None

    now = datetime.now(UTC)
    expires = now + timedelta(minutes=settings.guest_session_minutes)
    ttl = int((expires - now).total_seconds())
    device_hash = _hash_bind(device)
    ip_hash = _hash_bind(ip)
    stored["device_hash"] = device_hash
    stored["ip_hash"] = ip_hash
    await _save_session(jti, stored, ttl)

    refreshed = jwt.encode(
        _guest_jwt_claims(
            jti=jti,
            tenant_id=str(resolved_tenant_id),
            iat=int(now.timestamp()),
            exp=int(expires.timestamp()),
            device_hash=device_hash,
            ip_hash=ip_hash,
        ),
        _guest_signing_key(),
        algorithm="HS256",
    )
    _set_guest_cookies(request, response, token=refreshed, ttl=ttl)
    return {
        "expires_at": expires.isoformat(),
        "tenant_id": str(resolved_tenant_id),
        "tenant_bound": True,
        "session_minutes": settings.guest_session_minutes,
        "reused": True,
    }


async def mint_guest_session(
    request: Request,
    db: AsyncSession,
    *,
    response: Response,
    tenant_id: UUID | None = None,
) -> dict[str, Any]:
    settings = get_settings()
    if not settings.guest_quote_enabled:
        raise AuthorizationError("Guest quotes are disabled")

    require_trusted_origin(request)
    ip = client_ip(request)
    device = _guest_device_id(request)
    resolved_tenant_id = await resolve_guest_tenant_id(db, preferred=tenant_id)
    await ensure_tenant_issuance_branch(db, resolved_tenant_id)

    reused = await _try_reuse_guest_session(
        request,
        response=response,
        resolved_tenant_id=resolved_tenant_id,
        device=device,
    )
    if reused is not None:
        return reused

    # Rate-limit only brand-new capability cookies (not refresh/reuse).
    mint_limit = max(20, int(settings.guest_mint_limit_per_hour))
    if not await _rate_allow(f"rl:guest-mint-v2:{ip}", limit=mint_limit):
        raise ValidationAppError(
            "Too many new guest sessions from this network. Wait a minute and try again."
        )

    jti = str(uuid4())
    now = datetime.now(UTC)
    expires = now + timedelta(minutes=settings.guest_session_minutes)
    ttl = int((expires - now).total_seconds())

    session_payload = {
        "jti": jti,
        "tenant_id": str(resolved_tenant_id),
        "ip_hash": _hash_bind(ip),
        "device_hash": _hash_bind(device),
        "customers": [],
        "policies": [],
        "created_at": now.isoformat(),
    }
    await _save_session(jti, session_payload, ttl)

    token = jwt.encode(
        _guest_jwt_claims(
            jti=jti,
            tenant_id=str(resolved_tenant_id),
            iat=int(now.timestamp()),
            exp=int(expires.timestamp()),
            device_hash=session_payload["device_hash"],
            ip_hash=session_payload["ip_hash"],
        ),
        _guest_signing_key(),
        algorithm="HS256",
    )
    _set_guest_cookies(request, response, token=token, ttl=ttl)

    return {
        "expires_at": expires.isoformat(),
        "tenant_id": str(resolved_tenant_id),
        "tenant_bound": True,
        "session_minutes": settings.guest_session_minutes,
        "reused": False,
    }


async def load_guest_context(
    request: Request, db: AsyncSession
) -> GuestContext | None:
    settings = get_settings()
    if not settings.guest_quote_enabled:
        return None
    token = request.cookies.get(settings.guest_cookie_name)
    if not token:
        return None

    require_trusted_origin(request)

    from app.modules.system_config.service import SystemConfigService

    operational = await SystemConfigService(db).get_operational()
    if not operational.enabled:
        raise SystemUnavailableError(
            operational.reason or "The platform is temporarily switched off"
        )

    try:
        payload = _decode_guest_token(token)
    except JWTError as exc:
        raise AuthenticationError("Guest session is invalid or expired") from exc

    if payload.get("typ") != "guest":
        raise AuthenticationError("Guest session is invalid")

    jti = str(payload.get("jti") or "")
    stored = await _load_session(jti)
    if not stored:
        stored = _session_from_jwt(payload)
        if stored is None:
            raise AuthenticationError("Guest session has expired")
        settings_ttl = max(60, settings.guest_session_minutes * 60)
        await _save_session(jti, stored, settings_ttl)

    device = _guest_device_id(request)
    if not hmac.compare_digest(stored.get("device_hash", ""), _hash_bind(device)):
        raise AuthenticationError("Guest session device mismatch")
    ip = client_ip(request)
    expected_ip = stored.get("ip_hash", "")
    actual_ip_hash = _hash_bind(ip)
    if not hmac.compare_digest(expected_ip, actual_ip_hash):
        # Device + origin + CSRF still bind the session. End-user IP can shift
        # behind CGNAT / mobile handoff / multi-hop Cloud Run edges; refresh the
        # bound hash rather than failing the quote mid-flow.
        stored["ip_hash"] = actual_ip_hash
        await _save_session(
            jti, stored, max(60, settings.guest_session_minutes * 60)
        )

    # Do NOT apply a shared hourly budget here. Catalog loads + STK payment polls
    # alone exceed a low shared ceiling and lock legitimate guests out of quotes.
    # Expensive paths enforce their own limits (mint / submit / identity / agent /
    # catalog / payment-poll) below.

    tenant_id = UUID(str(stored["tenant_id"]))
    session_id = UUID(jti)

    guest = GuestContext(
        session_id=session_id,
        tenant_id=tenant_id,
        tenant_status=TenantStatus.ACTIVE.value,
        app_env=settings.app_env,
        jti=jti,
    )
    guest.bind()
    # Staff requests bind app.* through the auth query; guests had only the Python
    # context, so the database-side tenant policies had nothing to match on. With
    # FORCE RLS on the domain tables that is no longer optional.
    await set_rls_context(
        db,
        tenant_id=tenant_id,
        is_platform_admin=False,
        user_id=None,
        role_id=None,
    )
    if not stored.get("customers") or stored.get("from_jwt"):
        await _hydrate_guest_bindings(db, session_id, stored)
        stored.pop("from_jwt", None)
        await _save_session(jti, stored, max(60, settings.guest_session_minutes * 60))
    execution = guest.as_execution_context()
    request.state.guest_context = guest
    request.state.security_context = execution
    request.state.guest_session = stored
    request.state.guest_jti = jti
    return guest


# Looking a customer up by ID number is an identity probe. Guests also burn
# lookups while typing (debounced) and on save/returning-client handoff, so the
# ceiling has to leave room for a normal quote without blocking retries.
GUEST_IDENTITY_LOOKUPS_PER_SESSION = 40
GUEST_IDENTITY_LOOKUPS_PER_IP = 80
# Match the "few minutes" copy — a 1-hour lockout was stranding guests.
GUEST_IDENTITY_LOOKUP_WINDOW = 300
# Public picker is id/name only, but still origin-bound. A 5-minute window
# matches the error copy and survives SPA remounts without a 1-hour lockout.
GUEST_TENANT_LIST_PER_IP = 40
GUEST_TENANT_LIST_WINDOW = 300
GUEST_CSRF_BOOTSTRAP_PER_IP = 60
GUEST_CSRF_BOOTSTRAP_WINDOW = 300
GUEST_SUBMITS_PER_SESSION = 3
GUEST_SUBMIT_ATTEMPTS_PER_SESSION = 8
GUEST_SUBMITS_PER_IP = 10
GUEST_CLAIMS_PER_SESSION = 3
GUEST_CLAIM_ATTEMPTS_PER_SESSION = 8
GUEST_CLAIMS_PER_IP = 15
GUEST_CLAIM_FOLLOWUPS_PER_SESSION = 10
GUEST_CLAIM_FOLLOWUPS_PER_IP = 20
GUEST_CLAIM_RATE_WINDOW = 900
# Agent-code QR resolve — tight ceiling to blunt code-space sweeps.
GUEST_AGENT_LOOKUPS_PER_SESSION = 12
GUEST_AGENT_LOOKUPS_PER_IP = 30
GUEST_AGENT_LOOKUP_WINDOW = 600
# Catalog is read-only + cached; allow SPA remounts without a 1-hour lockout.
GUEST_CATALOG_PER_IP = 90
GUEST_CATALOG_WINDOW = 300
# STK status polls every ~2s for a few minutes — must not share the old API bucket.
GUEST_PAYMENT_POLL_PER_IP = 180
GUEST_PAYMENT_POLL_PER_SESSION = 120
GUEST_PAYMENT_POLL_WINDOW = 300
# Soft ceiling on premium quotes (Definite RTT) — still far above a normal wizard.
GUEST_PREMIUM_PER_IP = 40
GUEST_PREMIUM_PER_SESSION = 20
GUEST_PREMIUM_WINDOW = 300

# Self-service agent applications write a pending row an admin must review, so a
# person needs at most a couple of tries; anything more is spam.
GUEST_AGENT_APPLY_PER_SESSION = 3
GUEST_AGENT_APPLY_PER_IP = 8
GUEST_AGENT_APPLY_WINDOW = 3600


async def enforce_guest_agent_apply_limit(request: Request) -> None:
    """Bound self-service agent applications per session and network."""
    guest: GuestContext | None = getattr(request.state, "guest_context", None)
    if guest is None:
        raise AuthenticationError("Guest session is invalid or expired")
    jti = str(getattr(request.state, "guest_jti", None) or "")
    if not jti:
        raise AuthenticationError("Guest session is invalid or expired")
    ip = client_ip(request)
    allowed = await _rate_allow(
        f"rl:guest-agent-apply:{jti}",
        limit=GUEST_AGENT_APPLY_PER_SESSION,
        window=GUEST_AGENT_APPLY_WINDOW,
    )
    allowed = (
        await _rate_allow(
            f"rl:guest-agent-apply-ip:{ip}",
            limit=GUEST_AGENT_APPLY_PER_IP,
            window=GUEST_AGENT_APPLY_WINDOW,
        )
        and allowed
    )
    if not allowed:
        raise ValidationAppError(
            "Too many registration attempts. Please wait a while and try again."
        )


async def enforce_guest_agent_lookup_limit(request: Request) -> None:
    """Bound agent-code QR validation probes per session and network."""
    guest: GuestContext | None = getattr(request.state, "guest_context", None)
    if guest is None:
        raise AuthenticationError("Guest session is invalid or expired")
    jti = str(getattr(request.state, "guest_jti", None) or "")
    if not jti:
        raise AuthenticationError("Guest session is invalid or expired")
    ip = client_ip(request)
    allowed = await _rate_allow(
        f"rl:guest-agent:{jti}",
        limit=GUEST_AGENT_LOOKUPS_PER_SESSION,
        window=GUEST_AGENT_LOOKUP_WINDOW,
    )
    allowed = (
        await _rate_allow(
            f"rl:guest-agent-ip:{ip}",
            limit=GUEST_AGENT_LOOKUPS_PER_IP,
            window=GUEST_AGENT_LOOKUP_WINDOW,
        )
        and allowed
    )
    if not allowed:
        raise ValidationAppError(
            "Too many agent code checks. Please wait a few minutes and try again."
        )


async def enforce_guest_tenant_list_limit(request: Request) -> None:
    """Separate ceiling for the public agency picker — not the issuance API budget."""
    ip = client_ip(request)
    if not await _rate_allow(
        f"rl:guest-tenants-v2:{ip}",
        limit=GUEST_TENANT_LIST_PER_IP,
        window=GUEST_TENANT_LIST_WINDOW,
    ):
        raise ValidationAppError("Too many agency lookups. Please wait a few minutes.")


async def enforce_guest_csrf_bootstrap_limit(request: Request) -> None:
    """Cookie issuance only — must not share the agency-list budget."""
    ip = client_ip(request)
    if not await _rate_allow(
        f"rl:guest-csrf:{ip}",
        limit=GUEST_CSRF_BOOTSTRAP_PER_IP,
        window=GUEST_CSRF_BOOTSTRAP_WINDOW,
    ):
        raise ValidationAppError(
            "Too many guest session attempts. Please wait a few minutes."
        )


async def enforce_guest_catalog_limit(request: Request) -> None:
    """Catalog is cached server-side; still bound probes per network."""
    ip = client_ip(request)
    if not await _rate_allow(
        f"rl:guest-catalog:{ip}",
        limit=GUEST_CATALOG_PER_IP,
        window=GUEST_CATALOG_WINDOW,
    ):
        raise ValidationAppError(
            "Too many catalog requests. Please wait a moment and try again."
        )


async def enforce_guest_payment_poll_limit(request: Request) -> None:
    """STK confirmation polls — generous short window, separate from catalog."""
    guest: GuestContext | None = getattr(request.state, "guest_context", None)
    if guest is None:
        raise AuthenticationError("Guest session is invalid or expired")
    jti = str(getattr(request.state, "guest_jti", None) or "")
    if not jti:
        raise AuthenticationError("Guest session is invalid or expired")
    ip = client_ip(request)
    allowed = await _rate_allow(
        f"rl:guest-pay-poll:{jti}",
        limit=GUEST_PAYMENT_POLL_PER_SESSION,
        window=GUEST_PAYMENT_POLL_WINDOW,
    )
    allowed = (
        await _rate_allow(
            f"rl:guest-pay-poll-ip:{ip}",
            limit=GUEST_PAYMENT_POLL_PER_IP,
            window=GUEST_PAYMENT_POLL_WINDOW,
        )
        and allowed
    )
    if not allowed:
        raise ValidationAppError(
            "Too many payment status checks. Please wait a moment and try again."
        )


async def enforce_guest_premium_limit(request: Request) -> None:
    """Premium hits Definite — keep a soft ceiling without locking the wizard."""
    guest: GuestContext | None = getattr(request.state, "guest_context", None)
    if guest is None:
        raise AuthenticationError("Guest session is invalid or expired")
    jti = str(getattr(request.state, "guest_jti", None) or "")
    if not jti:
        raise AuthenticationError("Guest session is invalid or expired")
    ip = client_ip(request)
    allowed = await _rate_allow(
        f"rl:guest-premium:{jti}",
        limit=GUEST_PREMIUM_PER_SESSION,
        window=GUEST_PREMIUM_WINDOW,
    )
    allowed = (
        await _rate_allow(
            f"rl:guest-premium-ip:{ip}",
            limit=GUEST_PREMIUM_PER_IP,
            window=GUEST_PREMIUM_WINDOW,
        )
        and allowed
    )
    if not allowed:
        raise ValidationAppError(
            "Too many premium calculations. Please wait a moment and try again."
        )


async def enforce_guest_submit_limit(request: Request) -> None:
    """Bound guest newProposal attempts per session and network."""
    guest: GuestContext | None = getattr(request.state, "guest_context", None)
    if guest is None:
        raise AuthenticationError("Guest session is invalid or expired")
    jti = str(getattr(request.state, "guest_jti", None) or "")
    if not jti:
        raise AuthenticationError("Guest session is invalid or expired")
    ip = client_ip(request)
    allowed = await _rate_allow(
        f"rl:guest-submit-attempt:{jti}", limit=GUEST_SUBMIT_ATTEMPTS_PER_SESSION
    )
    allowed = await _rate_allow(f"rl:guest-submit-ip:{ip}", limit=GUEST_SUBMITS_PER_IP) and allowed
    if not allowed:
        raise ValidationAppError(
            "Too many quote submissions. Please wait a few minutes and try again."
        )


def _guest_submit_success_key(request: Request) -> str | None:
    jti = str(getattr(request.state, "guest_jti", None) or "")
    return f"rl:guest-submit-ok:{jti}" if jti else None


async def reserve_guest_submit_slot(request: Request) -> None:
    """Take one of the per-session newProposal slots. Caller must release on failure."""
    key = _guest_submit_success_key(request)
    if key is None:
        raise AuthenticationError("Guest session is invalid or expired")
    count = await _counter_incr(key)
    if count > GUEST_SUBMITS_PER_SESSION:
        await _counter_decr(key)
        raise ValidationAppError("This guest session has reached its quote limit.")


async def release_guest_submit_slot(request: Request) -> None:
    key = _guest_submit_success_key(request)
    if key is None:
        return
    await _counter_decr(key)


async def record_guest_submit_success(request: Request) -> None:
    return None


def _guest_claim_success_key(request: Request) -> str | None:
    jti = str(getattr(request.state, "guest_jti", None) or "")
    return f"rl:guest-claim-ok:{jti}" if jti else None


async def enforce_guest_claim_limit(request: Request) -> None:
    """Bound guest FNOL filing attempts — not lookup or follow-up."""
    guest: GuestContext | None = getattr(request.state, "guest_context", None)
    if guest is None:
        raise AuthenticationError("Guest session is invalid or expired")
    jti = str(getattr(request.state, "guest_jti", None) or "")
    if not jti:
        raise AuthenticationError("Guest session is invalid or expired")
    ip = client_ip(request)
    allowed = await _rate_allow(
        f"rl:guest-fnol:{jti}",
        limit=GUEST_CLAIM_ATTEMPTS_PER_SESSION,
        window=GUEST_CLAIM_RATE_WINDOW,
    )
    allowed = (
        await _rate_allow(
            f"rl:guest-fnol-ip:{ip}",
            limit=GUEST_CLAIMS_PER_IP,
            window=GUEST_CLAIM_RATE_WINDOW,
        )
        and allowed
    )
    if not allowed:
        raise ValidationAppError(
            "Too many claim attempts. Please wait a few minutes and try again."
        )


async def enforce_guest_claim_followup_limit(request: Request) -> None:
    """Bound messages on an already-proven guest claim."""
    guest: GuestContext | None = getattr(request.state, "guest_context", None)
    if guest is None:
        raise AuthenticationError("Guest session is invalid or expired")
    jti = str(getattr(request.state, "guest_jti", None) or "")
    if not jti:
        raise AuthenticationError("Guest session is invalid or expired")
    ip = client_ip(request)
    allowed = await _rate_allow(
        f"rl:guest-claim-msg:{jti}",
        limit=GUEST_CLAIM_FOLLOWUPS_PER_SESSION,
        window=GUEST_CLAIM_RATE_WINDOW,
    )
    allowed = (
        await _rate_allow(
            f"rl:guest-claim-msg-ip:{ip}",
            limit=GUEST_CLAIM_FOLLOWUPS_PER_IP,
            window=GUEST_CLAIM_RATE_WINDOW,
        )
        and allowed
    )
    if not allowed:
        raise ValidationAppError(
            "Too many follow-up messages. Please wait a few minutes and try again."
        )


async def reserve_guest_claim_slot(request: Request) -> None:
    """Take one of the per-session guest FNOL slots. Caller must release on failure."""
    key = _guest_claim_success_key(request)
    if key is None:
        raise AuthenticationError("Guest session is invalid or expired")
    count = await _counter_incr(key)
    if count > GUEST_CLAIMS_PER_SESSION:
        await _counter_decr(key)
        raise ValidationAppError("This guest session has reached its claim limit.")


async def release_guest_claim_slot(request: Request) -> None:
    key = _guest_claim_success_key(request)
    if key is None:
        return
    await _counter_decr(key)


async def enforce_guest_identity_lookup_limit(request: Request) -> None:
    """Rate-limit guest customer lookups per session and per network."""
    guest: GuestContext | None = getattr(request.state, "guest_context", None)
    if guest is None:
        return
    jti = str(getattr(request.state, "guest_jti", None) or "")
    ip = client_ip(request)
    allowed = await _rate_allow(
        f"rl:guest-identity-ip:{ip}",
        limit=GUEST_IDENTITY_LOOKUPS_PER_IP,
        window=GUEST_IDENTITY_LOOKUP_WINDOW,
    )
    if jti:
        allowed = (
            await _rate_allow(
                f"rl:guest-identity:{jti}",
                limit=GUEST_IDENTITY_LOOKUPS_PER_SESSION,
                window=GUEST_IDENTITY_LOOKUP_WINDOW,
            )
            and allowed
        )
    if not allowed:
        raise ValidationAppError(
            "Too many client lookups. Please wait a few minutes and try again."
        )


async def bind_guest_customer(request: Request, customer_id: UUID) -> None:
    jti = getattr(request.state, "guest_jti", None)
    stored = getattr(request.state, "guest_session", None)
    if not jti or not isinstance(stored, dict):
        return
    customers = list(stored.get("customers") or [])
    cid = str(customer_id)
    if cid not in customers:
        customers.append(cid)
        stored["customers"] = customers[-50:]
        await _update_session(jti, stored)
        request.state.guest_session = stored


async def bind_guest_policy(request: Request, policy_id: UUID) -> None:
    jti = getattr(request.state, "guest_jti", None)
    stored = getattr(request.state, "guest_session", None)
    if not jti or not isinstance(stored, dict):
        return
    policies = list(stored.get("policies") or [])
    pid = str(policy_id)
    if pid not in policies:
        policies.append(pid)
        stored["policies"] = policies[-50:]
        await _update_session(jti, stored)
        request.state.guest_session = stored


def assert_guest_owns_customer(request: Request, customer_id: UUID) -> None:
    guest: GuestContext | None = getattr(request.state, "guest_context", None)
    if guest is None:
        return
    stored = getattr(request.state, "guest_session", None) or {}
    allowed = {str(x) for x in (stored.get("customers") or [])}
    if str(customer_id) not in allowed:
        raise AuthorizationError("Guest session cannot use this customer")


def assert_guest_owns_policy(request: Request, policy_id: UUID) -> None:
    guest: GuestContext | None = getattr(request.state, "guest_context", None)
    if guest is None:
        return
    stored = getattr(request.state, "guest_session", None) or {}
    allowed = {str(x) for x in (stored.get("policies") or [])}
    if str(policy_id) not in allowed:
        raise AuthorizationError("Guest session cannot use this policy")


async def bind_guest_claim(request: Request, claim_id: UUID) -> None:
    jti = getattr(request.state, "guest_jti", None)
    stored = getattr(request.state, "guest_session", None)
    if not jti or not isinstance(stored, dict):
        return
    claims = list(stored.get("claims") or [])
    cid = str(claim_id)
    if cid not in claims:
        claims.append(cid)
        stored["claims"] = claims[-50:]
        await _update_session(jti, stored)
        request.state.guest_session = stored


def assert_guest_owns_claim(request: Request, claim_id: UUID) -> None:
    guest: GuestContext | None = getattr(request.state, "guest_context", None)
    if guest is None:
        raise AuthorizationError("Guest session cannot use this claim")
    stored = getattr(request.state, "guest_session", None) or {}
    allowed = {str(x) for x in (stored.get("claims") or [])}
    if str(claim_id) not in allowed:
        raise AuthorizationError("Guest session cannot use this claim")
