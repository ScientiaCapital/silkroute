"""Tests for silkroute.db.pool — asyncpg connection pool singleton."""

from __future__ import annotations

from unittest.mock import AsyncMock, patch

import pytest


@pytest.fixture(autouse=True)
def _reset_pool() -> None:
    """Ensure pool singleton is reset between tests."""
    import silkroute.db.pool as pool_mod

    pool_mod._pool = None
    yield
    pool_mod._pool = None


async def test_get_pool_creates_pool() -> None:
    """get_pool() creates a connection pool on first call."""
    mock_pool = AsyncMock()

    with patch("silkroute.db.pool.asyncpg.create_pool", new_callable=AsyncMock, return_value=mock_pool):
        from silkroute.db.pool import get_pool

        result = await get_pool()

    assert result is mock_pool


async def test_get_pool_returns_cached() -> None:
    """get_pool() returns the same pool on subsequent calls."""
    mock_pool = AsyncMock()

    with patch("silkroute.db.pool.asyncpg.create_pool", new_callable=AsyncMock, return_value=mock_pool) as create:
        from silkroute.db.pool import get_pool

        pool1 = await get_pool()
        pool2 = await get_pool()

    assert pool1 is pool2
    create.assert_awaited_once()  # Only created once


async def test_get_pool_returns_none_on_failure() -> None:
    """get_pool() returns None when PostgreSQL is unreachable."""
    with patch("silkroute.db.pool.asyncpg.create_pool", new_callable=AsyncMock, side_effect=OSError("connection refused")):
        from silkroute.db.pool import get_pool

        result = await get_pool()

    assert result is None


async def test_close_pool_closes_and_resets() -> None:
    """close_pool() closes the pool and allows re-creation."""
    mock_pool = AsyncMock()

    with patch("silkroute.db.pool.asyncpg.create_pool", new_callable=AsyncMock, return_value=mock_pool):
        from silkroute.db.pool import close_pool, get_pool

        await get_pool()
        await close_pool()

    mock_pool.close.assert_awaited_once()

    import silkroute.db.pool as pool_mod

    assert pool_mod._pool is None


async def test_close_pool_noop_when_no_pool() -> None:
    """close_pool() does nothing when no pool exists."""
    from silkroute.db.pool import close_pool

    # Should not raise
    await close_pool()


def test_mask_url_hides_password() -> None:
    """_mask_url replaces password in PostgreSQL URLs."""
    from silkroute.db.pool import _mask_url

    assert _mask_url("postgresql://user:secret@host:5432/db") == "postgresql://user:***@host:5432/db"


def test_mask_url_no_password() -> None:
    """_mask_url returns URL unchanged when no password present."""
    from silkroute.db.pool import _mask_url

    assert _mask_url("postgresql://host:5432/db") == "postgresql://host:5432/db"
