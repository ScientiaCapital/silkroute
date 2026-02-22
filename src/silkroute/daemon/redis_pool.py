"""Async Redis client singleton for daemon mode.

Mirrors the db/pool.py pattern: lazy-initialized on first access,
asyncio.Lock-guarded, graceful failure if Redis is unreachable.
"""

from __future__ import annotations

import asyncio
import functools
from collections.abc import Callable

import redis.asyncio as aioredis
import structlog

from silkroute.config.settings import DatabaseConfig

log = structlog.get_logger()

_redis: aioredis.Redis | None = None
_redis_lock: asyncio.Lock = asyncio.Lock()

# Retry settings
_RETRY_DELAYS = (0.1, 0.5, 2.0)


def redis_retry[F: Callable[..., object]](fn: F) -> F:
    """Decorator: retry async Redis operations with exponential backoff.

    Retries up to 3 times on Redis connection/timeout errors before
    propagating the exception to the caller.
    """

    @functools.wraps(fn)
    async def wrapper(*args: object, **kwargs: object) -> object:
        last_exc: Exception | None = None
        for delay in _RETRY_DELAYS:
            try:
                return await fn(*args, **kwargs)
            except (aioredis.ConnectionError, aioredis.TimeoutError, OSError) as exc:
                last_exc = exc
                log.warning(
                    "redis_retry",
                    fn=fn.__name__,
                    delay=delay,
                    error=str(exc),
                )
                await asyncio.sleep(delay)
        raise last_exc  # type: ignore[misc]

    return wrapper  # type: ignore[return-value]


async def get_redis() -> aioredis.Redis | None:
    """Return the shared Redis client, creating it on first call.

    Returns None if Redis is unreachable — callers must handle this.
    Uses asyncio.Lock to prevent duplicate client creation under concurrent access.
    """
    global _redis  # noqa: PLW0603
    if _redis is not None:
        return _redis

    async with _redis_lock:
        # Double-check after acquiring lock
        if _redis is not None:
            return _redis

        try:
            cfg = DatabaseConfig()
            client = aioredis.from_url(
                cfg.redis_url,
                decode_responses=True,
                max_connections=10,
            )
            await client.ping()
            _redis = client
            log.info("redis_connected", redis_url=_mask_redis_url(cfg.redis_url))
        except (aioredis.ConnectionError, aioredis.TimeoutError, OSError) as exc:
            log.warning("redis_connection_failed", error=str(exc))
            _redis = None

    return _redis


async def close_redis() -> None:
    """Shut down the Redis client if it exists."""
    global _redis  # noqa: PLW0603
    if _redis is not None:
        await _redis.aclose()
        _redis = None
        log.info("redis_closed")


def _mask_redis_url(url: str) -> str:
    """Mask password in a Redis URL for safe logging.

    redis://:password@host:port/db → redis://:***@host:port/db
    """
    if "@" in url and ":" in url.split("@")[0]:
        prefix, rest = url.split("@", 1)
        user_part = prefix.rsplit(":", 1)[0]
        return f"{user_part}:***@{rest}"
    return url
