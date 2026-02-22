"""Asyncpg connection pool singleton.

Lazy-initialized on first access. Graceful failure: if PostgreSQL is
unreachable, get_pool() returns None and callers skip DB operations.
"""

from __future__ import annotations

import asyncpg
import structlog

from silkroute.config.settings import DatabaseConfig

log = structlog.get_logger()

_pool: asyncpg.Pool | None = None


async def get_pool() -> asyncpg.Pool | None:
    """Return the shared connection pool, creating it on first call.

    Returns None if PostgreSQL is unreachable — callers must handle this.
    """
    global _pool  # noqa: PLW0603
    if _pool is not None:
        return _pool

    try:
        cfg = DatabaseConfig()
        _pool = await asyncpg.create_pool(
            cfg.postgres_url,
            min_size=1,
            max_size=5,
            command_timeout=10,
        )
        log.info("db_pool_created", postgres_url=_mask_url(cfg.postgres_url))
    except (OSError, asyncpg.PostgresError) as exc:
        log.warning("db_pool_failed", error=str(exc))
        _pool = None

    return _pool


async def close_pool() -> None:
    """Shut down the connection pool if it exists."""
    global _pool  # noqa: PLW0603
    if _pool is not None:
        await _pool.close()
        _pool = None
        log.info("db_pool_closed")


def _mask_url(url: str) -> str:
    """Mask password in a PostgreSQL URL for safe logging."""
    # postgresql://user:password@host:port/db → postgresql://user:***@host:port/db
    if "@" in url and ":" in url.split("@")[0]:
        prefix, rest = url.split("@", 1)
        user_part = prefix.rsplit(":", 1)[0]
        return f"{user_part}:***@{rest}"
    return url
