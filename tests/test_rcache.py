import asyncio
import json

from api import rcache


class FakeRedis:
    def __init__(self):
        self.values = {}
        self.ttls = {}

    async def get(self, key):
        return self.values.get(key)

    async def set(self, key, value, ex):
        self.values[key] = value
        self.ttls[key] = ex
        return True

    async def aclose(self):
        return None


def test_rcache_round_trips_embedding_with_ttl(monkeypatch):
    fake = FakeRedis()

    async def client():
        return fake

    monkeypatch.setattr(rcache, "_redis_client", client)
    monkeypatch.setattr(rcache.settings, "redis_embedding_cache_ttl_seconds", 1800)
    monkeypatch.setattr(rcache.settings, "api_key", "test-only-cache-key-secret")

    async def scenario():
        await rcache.set_embedding("embed-v1", 3, "texto privado", [0.1, 0.2, 0.3])
        result = await rcache.get_embedding("embed-v1", 3, "texto privado")
        assert result == [0.1, 0.2, 0.3]

    asyncio.run(scenario())
    assert len(fake.values) == 1
    key = next(iter(fake.values))
    assert "texto privado" not in key
    assert fake.ttls[key] == 1800


def test_rcache_rejects_corrupt_or_wrong_dimension_value(monkeypatch):
    fake = FakeRedis()

    async def client():
        return fake

    monkeypatch.setattr(rcache, "_redis_client", client)
    monkeypatch.setattr(rcache.settings, "api_key", "test-only-cache-key-secret")

    async def scenario():
        key = rcache._cache_key("embed-v1", 2, "hello")
        fake.values[key] = json.dumps([0.1, float("nan")])
        assert await rcache.get_embedding("embed-v1", 2, "hello") is None
        fake.values[key] = json.dumps([0.1])
        assert await rcache.get_embedding("embed-v1", 2, "hello") is None

    asyncio.run(scenario())


def test_rcache_bypasses_when_disabled(monkeypatch):
    monkeypatch.setattr(rcache.settings, "redis_cache_enabled", False)

    async def scenario():
        assert await rcache.get_embedding("embed-v1", 2, "hello") is None

    asyncio.run(scenario())


def test_rcache_fails_open_when_redis_is_unavailable(monkeypatch):
    async def unavailable():
        raise ConnectionError("redis offline")

    monkeypatch.setattr(rcache, "_redis_client", unavailable)

    async def scenario():
        assert await rcache.get_embedding("embed-v1", 2, "hello") is None
        await rcache.set_embedding("embed-v1", 2, "hello", [0.1, 0.2])
        assert await rcache.ping_cache() is False

    asyncio.run(scenario())
