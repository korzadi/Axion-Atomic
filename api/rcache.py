"""RCache: caché Redis de embeddings para el bot AXION.

No almacena prompts completos, respuestas del modelo, sesiones ni datos de facturación.
Solo conserva vectores de embedding derivados, con clave SHA-256 y TTL. Redis es
opcional: cualquier fallo de caché degrada a la llamada normal a Ollama.
"""
from __future__ import annotations

import hashlib
import json
import logging
import math

from api.config import settings

logger = logging.getLogger("axion.rcache")
_client = None


def _cache_key(model: str, dimension: int, text: str) -> str:
    digest = hashlib.sha256(
        (model + "\0" + str(dimension) + "\0" + text).encode("utf-8")
    ).hexdigest()
    return "axion:rcache:embedding:v1:" + digest


async def _redis_client():
    global _client
    if not settings.redis_cache_enabled or not settings.redis_url:
        return None
    if _client is None:
        from redis.asyncio import Redis
        _client = Redis.from_url(
            settings.redis_url,
            decode_responses=True,
            socket_connect_timeout=settings.redis_socket_timeout_seconds,
            socket_timeout=settings.redis_socket_timeout_seconds,
            health_check_interval=30,
            max_connections=16,
        )
    return _client


async def get_embedding(model: str, dimension: int, text: str) -> list[float] | None:
    if len(text) > 20000:
        return None
    try:
        client = await _redis_client()
        if client is None:
            return None
        raw = await client.get(_cache_key(model, dimension, text))
        if raw is None:
            return None
        value = json.loads(raw)
        if not isinstance(value, list) or len(value) != dimension:
            return None
        vector = [float(item) for item in value]
        if not all(math.isfinite(item) for item in vector):
            return None
        return vector
    except Exception:
        logger.warning("RCache embedding read unavailable; bypassing cache")
        return None


async def set_embedding(model: str, dimension: int, text: str, vector: list[float]) -> None:
    if len(text) > 20000 or len(vector) != dimension:
        return
    try:
        client = await _redis_client()
        if client is None:
            return
        ttl = max(60, min(int(settings.redis_embedding_cache_ttl_seconds), 86400))
        await client.set(
            _cache_key(model, dimension, text),
            json.dumps(vector, separators=(",", ":"), allow_nan=False),
            ex=ttl,
        )
    except Exception:
        logger.warning("RCache embedding write unavailable; bypassing cache")


async def close_cache() -> None:
    global _client
    if _client is not None:
        try:
            await _client.aclose()
        finally:
            _client = None


async def ping_cache() -> bool:
    try:
        client = await _redis_client()
        return bool(await client.ping()) if client is not None else False
    except Exception:
        return False
