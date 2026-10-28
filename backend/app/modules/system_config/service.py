"""System configuration service — DB truth, optimistic concurrency, audited writes."""

from __future__ import annotations

import threading
import time
from datetime import UTC, datetime
from typing import Any
from uuid import UUID

from sqlalchemy.ext.asyncio import AsyncSession

from app.core.exceptions import ConflictError, ServiceDisabledError, ValidationAppError
from app.modules.audit.service import AuditService
from app.modules.system_config.constants import (
    CHANNEL_KEYS,
    DEFAULT_CHANNELS,
    DEFAULT_SERVICES,
    KEY_NOTIFICATION_CHANNELS,
    KEY_OPERATIONAL,
    KEY_SERVICES,
    SERVICE_KEYS,
)
from app.modules.system_config.models import SystemSetting
from app.modules.system_config.schemas import (
    ChannelState,
    NotificationChannelsState,
    OperationalState,
    ServicesState,
    SystemConfigSnapshot,
)

# Short process cache — invalidated on every write. DB remains source of truth.
_CACHE_TTL_S = 2.0
_cache_lock = threading.Lock()
_cache: dict[str, tuple[float, dict[str, Any], int]] = {}


def _cache_get(key: str) -> tuple[dict[str, Any], int] | None:
    with _cache_lock:
        row = _cache.get(key)
        if not row:
            return None
        expires_at, value, version = row
        if time.monotonic() > expires_at:
            _cache.pop(key, None)
            return None
        return value, version


def _cache_set(key: str, value: dict[str, Any], version: int) -> None:
    with _cache_lock:
        _cache[key] = (time.monotonic() + _CACHE_TTL_S, value, version)


def invalidate_system_config_cache(key: str | None = None) -> None:
    with _cache_lock:
        if key is None:
            _cache.clear()
        else:
            _cache.pop(key, None)


class SystemConfigService:
    def __init__(self, session: AsyncSession) -> None:
        self.session = session
        self.audit = AuditService(session)

    async def _load(self, key: str) -> SystemSetting | None:
        return await self.session.get(SystemSetting, key)

    async def _get_value(self, key: str, *, live: bool = False) -> tuple[dict[str, Any], int]:
        if not live:
            cached = _cache_get(key)
            if cached is not None:
                return cached
        row = await self._load(key)
        if row is None:
            defaults = {
                KEY_OPERATIONAL: {
                    "enabled": True,
                    "reason": None,
                    "disabled_at": None,
                    "disabled_by": None,
                },
                KEY_SERVICES: dict(DEFAULT_SERVICES),
                KEY_NOTIFICATION_CHANNELS: {k: dict(v) for k, v in DEFAULT_CHANNELS.items()},
            }
            return defaults.get(key, {}), 1
        value = dict(row.value or {})
        _cache_set(key, value, row.version)
        return value, row.version

    async def get_operational(self, *, live: bool = False) -> OperationalState:
        value, version = await self._get_value(KEY_OPERATIONAL, live=live)
        return OperationalState(
            enabled=bool(value.get("enabled", True)),
            reason=value.get("reason"),
            disabled_at=value.get("disabled_at"),
            disabled_by=str(value["disabled_by"]) if value.get("disabled_by") else None,
            version=version,
        )

    async def get_services(self, *, live: bool = False) -> ServicesState:
        value, version = await self._get_value(KEY_SERVICES, live=live)
        services = {k: bool(value.get(k, DEFAULT_SERVICES[k])) for k in SERVICE_KEYS}
        return ServicesState(services=services, version=version)

    async def get_notification_channels(self, *, live: bool = False) -> NotificationChannelsState:
        value, version = await self._get_value(KEY_NOTIFICATION_CHANNELS, live=live)
        channels: dict[str, ChannelState] = {}
        for key in CHANNEL_KEYS:
            raw = value.get(key) or DEFAULT_CHANNELS[key]
            if isinstance(raw, dict):
                channels[key] = ChannelState(enabled=bool(raw.get("enabled", True)))
            else:
                channels[key] = ChannelState(enabled=bool(raw))
        return NotificationChannelsState(channels=channels, version=version)

    async def snapshot(self) -> SystemConfigSnapshot:
        return SystemConfigSnapshot(
            operational=await self.get_operational(),
            services=await self.get_services(),
            notification_channels=await self.get_notification_channels(),
        )

    async def is_system_enabled(self, *, live: bool = False) -> bool:
        return (await self.get_operational(live=live)).enabled

    async def is_service_enabled(self, service: str, *, live: bool = False) -> bool:
        if service not in SERVICE_KEYS:
            raise ValidationAppError(f"Unknown service: {service}")
        return (await self.get_services(live=live)).services.get(service, True)

    async def is_channel_enabled(self, channel: str, *, live: bool = False) -> bool:
        key = channel.upper()
        channels = (await self.get_notification_channels(live=live)).channels
        state = channels.get(key)
        return bool(state and state.enabled)

    async def outbound_allowed(self, channel: str, *, live: bool = True) -> bool:
        """Live DB flags: platform on, notifications service on, and this channel on."""
        if not await self.is_system_enabled(live=live):
            return False
        if not await self.is_service_enabled("notifications", live=live):
            return False
        return await self.is_channel_enabled(channel, live=live)

    async def require_service(self, service: str) -> None:
        if not await self.is_service_enabled(service, live=True):
            raise ServiceDisabledError(f"Service '{service}' is switched off")

    async def require_channel(self, channel: str) -> None:
        if not await self.is_channel_enabled(channel, live=True):
            raise ServiceDisabledError(f"Notification channel '{channel}' is switched off")

    async def require_outbound(self, channel: str) -> None:
        if not await self.is_system_enabled(live=True):
            raise ServiceDisabledError("Star Serve is switched off")
        await self.require_service("notifications")
        await self.require_channel(channel)

    async def _write(
        self,
        *,
        key: str,
        value: dict[str, Any],
        expected_version: int,
        actor_id: UUID,
        action: str,
        reason: str,
        tenant_id: UUID | None,
        ip_address: str | None = None,
        user_agent: str | None = None,
    ) -> SystemSetting:
        row = await self._load(key)
        if row is None:
            raise ValidationAppError(f"Unknown system setting: {key}")
        if row.version != expected_version:
            raise ConflictError(
                "Configuration was updated by someone else — reload and try again",
                details=[{"expected_version": expected_version, "current_version": row.version}],
            )
        previous = dict(row.value or {})
        row.value = value
        row.version = row.version + 1
        row.updated_by = actor_id
        row.updated_at = datetime.now(UTC)
        await self.session.flush()
        invalidate_system_config_cache(key)
        await self.audit.record(
            action=action,
            resource="system_setting",
            resource_id=key,
            tenant_id=tenant_id,
            user_id=actor_id,
            ip_address=ip_address,
            user_agent=user_agent,
            message=reason,
            metadata={"previous": previous, "next": value, "version": row.version},
        )
        return row

    async def set_operational(
        self,
        *,
        enabled: bool,
        reason: str,
        expected_version: int,
        actor_id: UUID,
        tenant_id: UUID | None,
        ip_address: str | None = None,
        user_agent: str | None = None,
    ) -> OperationalState:
        now = datetime.now(UTC).isoformat()
        value: dict[str, Any] = {
            "enabled": enabled,
            "reason": reason if not enabled else None,
            "disabled_at": None if enabled else now,
            "disabled_by": None if enabled else str(actor_id),
        }
        await self._write(
            key=KEY_OPERATIONAL,
            value=value,
            expected_version=expected_version,
            actor_id=actor_id,
            action="system.operational_change",
            reason=reason,
            tenant_id=tenant_id,
            ip_address=ip_address,
            user_agent=user_agent,
        )
        return await self.get_operational()

    async def set_services(
        self,
        *,
        services: dict[str, bool],
        reason: str,
        expected_version: int,
        actor_id: UUID,
        tenant_id: UUID | None,
        ip_address: str | None = None,
        user_agent: str | None = None,
    ) -> ServicesState:
        unknown = set(services) - SERVICE_KEYS
        if unknown:
            raise ValidationAppError(f"Unknown services: {', '.join(sorted(unknown))}")
        merged = {k: bool(services.get(k, DEFAULT_SERVICES[k])) for k in SERVICE_KEYS}
        await self._write(
            key=KEY_SERVICES,
            value=merged,
            expected_version=expected_version,
            actor_id=actor_id,
            action="system.services_change",
            reason=reason,
            tenant_id=tenant_id,
            ip_address=ip_address,
            user_agent=user_agent,
        )
        return await self.get_services()

    async def set_notification_channels(
        self,
        *,
        channels: dict[str, ChannelState],
        reason: str,
        expected_version: int,
        actor_id: UUID,
        tenant_id: UUID | None,
        ip_address: str | None = None,
        user_agent: str | None = None,
    ) -> NotificationChannelsState:
        unknown = set(channels) - CHANNEL_KEYS
        if unknown:
            raise ValidationAppError(f"Unknown channels: {', '.join(sorted(unknown))}")
        merged = {
            k: {"enabled": bool(channels[k].enabled if k in channels else DEFAULT_CHANNELS[k]["enabled"])}
            for k in CHANNEL_KEYS
        }
        # Keep unspecified channels from current DB state
        current, _ = await self._get_value(KEY_NOTIFICATION_CHANNELS)
        for k in CHANNEL_KEYS:
            if k not in channels:
                raw = current.get(k) or DEFAULT_CHANNELS[k]
                merged[k] = {
                    "enabled": bool(raw.get("enabled", True)) if isinstance(raw, dict) else bool(raw)
                }
        await self._write(
            key=KEY_NOTIFICATION_CHANNELS,
            value=merged,
            expected_version=expected_version,
            actor_id=actor_id,
            action="system.notification_channels_change",
            reason=reason,
            tenant_id=tenant_id,
            ip_address=ip_address,
            user_agent=user_agent,
        )
        return await self.get_notification_channels()
