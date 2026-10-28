"""Reference-data cache — process L1 + optional Redis L2 (safe, non-PII).

Cloud Run often has no Redis. An in-process TTL cache still collapses repeated
Definite ``products`` / ``makes`` RTTs within each instance.
"""

from __future__ import annotations

import json
import time
from threading import Lock
from typing import Any

from app.core.logging import get_logger

logger = get_logger(__name__)

PRODUCTS_TTL_SECONDS = 3600
MAKES_TTL_SECONDS = 3600
REASONS_TTL_SECONDS = 3600
# Shorter L1 so each Cloud Run instance stays fresh without Redis.
LOCAL_TTL_SECONDS = 900


class ReferenceDataCache:
    def __init__(self, redis_client: Any | None = None) -> None:
        self.redis = redis_client
        self._local: dict[str, tuple[float, list[dict[str, Any]]]] = {}
        self._lock = Lock()

    def _key(self, kind: str, tenant_id: str) -> str:
        return f"ref:{kind}:tenant:{tenant_id}"

    def _local_get(self, key: str) -> list[dict[str, Any]] | None:
        with self._lock:
            hit = self._local.get(key)
            if hit is None:
                return None
            expires_at, data = hit
            if time.monotonic() >= expires_at:
                self._local.pop(key, None)
                return None
            return data

    def _local_set(self, key: str, payload: list[dict[str, Any]], ttl: int) -> None:
        with self._lock:
            self._local[key] = (time.monotonic() + max(1, ttl), payload)

    def _local_delete(self, key: str) -> None:
        with self._lock:
            self._local.pop(key, None)

    async def get_json(self, kind: str, tenant_id: str) -> list[dict[str, Any]] | None:
        key = self._key(kind, tenant_id)
        local = self._local_get(key)
        if local is not None:
            return local

        if self.redis is None:
            return None
        try:
            raw = await self.redis.get(key)
            if not raw:
                return None
            data = json.loads(raw)
            if not isinstance(data, list):
                return None
            self._local_set(key, data, LOCAL_TTL_SECONDS)
            return data
        except Exception:
            logger.warning("reference_cache_get_failed", kind=kind)
            return None

    async def set_json(
        self,
        kind: str,
        tenant_id: str,
        payload: list[dict[str, Any]],
        ttl: int,
    ) -> None:
        key = self._key(kind, tenant_id)
        local_ttl = min(ttl, LOCAL_TTL_SECONDS) if self.redis is None else min(ttl, LOCAL_TTL_SECONDS)
        self._local_set(key, payload, local_ttl if self.redis is None else LOCAL_TTL_SECONDS)

        if self.redis is None:
            return
        try:
            await self.redis.set(key, json.dumps(payload), ex=ttl)
        except Exception:
            logger.warning("reference_cache_set_failed", kind=kind)

    async def invalidate(self, kind: str, tenant_id: str) -> None:
        key = self._key(kind, tenant_id)
        self._local_delete(key)
        if self.redis is None:
            return
        try:
            await self.redis.delete(key)
        except Exception:
            logger.warning("reference_cache_invalidate_failed", kind=kind)
