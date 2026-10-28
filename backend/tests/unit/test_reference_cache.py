"""Reference data cache — process L1 without Redis."""

import asyncio

import pytest

from app.modules.products.cache import ReferenceDataCache


@pytest.mark.asyncio
async def test_process_local_cache_roundtrip_without_redis() -> None:
    cache = ReferenceDataCache(redis_client=None)
    payload = [{"code": "MOTOR", "name": "Motor"}]
    assert await cache.get_json("products", "tenant-a") is None
    await cache.set_json("products", "tenant-a", payload, ttl=60)
    hit = await cache.get_json("products", "tenant-a")
    assert hit == payload
    await cache.invalidate("products", "tenant-a")
    assert await cache.get_json("products", "tenant-a") is None


@pytest.mark.asyncio
async def test_process_local_cache_expires() -> None:
    cache = ReferenceDataCache(redis_client=None)
    key = cache._key("makes", "tenant-b")  # noqa: SLF001
    cache._local_set(key, [{"code": "TOYOTA"}], ttl=1)  # noqa: SLF001
    assert await cache.get_json("makes", "tenant-b") is not None
    await asyncio.sleep(1.05)
    assert await cache.get_json("makes", "tenant-b") is None
