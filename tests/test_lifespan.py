"""Tests for the lifespan context manager in silkroute.api.app.

Tests the full startup/teardown lifecycle for Redis, Postgres, and
SkillRegistry without requiring real infrastructure.
"""

from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from fastapi import FastAPI

from silkroute.api.app import lifespan
from silkroute.config.settings import SilkRouteSettings
from silkroute.daemon.queue import TaskQueue


@pytest.fixture
def lifespan_app(test_settings: SilkRouteSettings) -> FastAPI:
    """Create a minimal FastAPI app with settings pre-attached."""
    app = FastAPI()
    app.state.settings = test_settings
    return app


@pytest.mark.asyncio
@patch("silkroute.api.app.asyncpg")
@patch("silkroute.api.app.aioredis")
async def test_redis_connect_success(
    mock_aioredis: MagicMock, mock_asyncpg: MagicMock, lifespan_app: FastAPI
) -> None:
    """app.state.redis and app.state.queue are set when Redis is reachable."""
    mock_redis_client = AsyncMock()
    mock_redis_client.ping = AsyncMock(return_value=True)
    mock_redis_client.get = AsyncMock(return_value=None)
    mock_aioredis.from_url.return_value = mock_redis_client
    mock_aioredis.ConnectionError = ConnectionError
    mock_aioredis.TimeoutError = TimeoutError

    mock_pool = AsyncMock()
    mock_asyncpg.create_pool = AsyncMock(return_value=mock_pool)
    mock_asyncpg.PostgresError = Exception
    mock_asyncpg.InterfaceError = Exception

    async with lifespan(lifespan_app):
        assert lifespan_app.state.redis is mock_redis_client
        assert isinstance(lifespan_app.state.queue, TaskQueue)


@pytest.mark.asyncio
@patch("silkroute.api.app.asyncpg")
@patch("silkroute.api.app.aioredis")
async def test_redis_connect_failure(
    mock_aioredis: MagicMock, mock_asyncpg: MagicMock, lifespan_app: FastAPI
) -> None:
    """app.state.redis and app.state.queue are None when Redis raises ConnectionError."""
    mock_aioredis.from_url.side_effect = ConnectionError("refused")
    mock_aioredis.ConnectionError = ConnectionError
    mock_aioredis.TimeoutError = TimeoutError

    mock_pool = AsyncMock()
    mock_asyncpg.create_pool = AsyncMock(return_value=mock_pool)
    mock_asyncpg.PostgresError = Exception
    mock_asyncpg.InterfaceError = Exception

    async with lifespan(lifespan_app):
        assert lifespan_app.state.redis is None
        assert lifespan_app.state.queue is None


@pytest.mark.asyncio
@patch("silkroute.api.app.asyncpg")
@patch("silkroute.api.app.aioredis")
async def test_postgres_connect_success(
    mock_aioredis: MagicMock, mock_asyncpg: MagicMock, lifespan_app: FastAPI
) -> None:
    """app.state.db_pool is set when Postgres is reachable."""
    mock_redis_client = AsyncMock()
    mock_redis_client.ping = AsyncMock(return_value=True)
    mock_redis_client.get = AsyncMock(return_value=None)
    mock_aioredis.from_url.return_value = mock_redis_client
    mock_aioredis.ConnectionError = ConnectionError
    mock_aioredis.TimeoutError = TimeoutError

    mock_pool = AsyncMock()
    mock_asyncpg.create_pool = AsyncMock(return_value=mock_pool)
    mock_asyncpg.PostgresError = Exception
    mock_asyncpg.InterfaceError = Exception

    async with lifespan(lifespan_app):
        assert lifespan_app.state.db_pool is mock_pool


@pytest.mark.asyncio
@patch("silkroute.api.app.asyncpg")
@patch("silkroute.api.app.aioredis")
async def test_postgres_connect_failure(
    mock_aioredis: MagicMock, mock_asyncpg: MagicMock, lifespan_app: FastAPI
) -> None:
    """app.state.db_pool is None when asyncpg.create_pool raises OSError."""
    # Redis succeeds
    mock_redis_client = AsyncMock()
    mock_redis_client.ping = AsyncMock(return_value=True)
    mock_redis_client.get = AsyncMock(return_value=None)
    mock_aioredis.from_url.return_value = mock_redis_client
    mock_aioredis.ConnectionError = ConnectionError
    mock_aioredis.TimeoutError = TimeoutError

    # Postgres fails
    mock_asyncpg.create_pool = AsyncMock(side_effect=OSError("connection refused"))
    mock_asyncpg.PostgresError = Exception
    mock_asyncpg.InterfaceError = Exception

    async with lifespan(lifespan_app):
        assert lifespan_app.state.db_pool is None


@pytest.mark.asyncio
@patch("silkroute.api.app.asyncpg")
@patch("silkroute.api.app.aioredis")
async def test_skill_registry_initialized(
    mock_aioredis: MagicMock, mock_asyncpg: MagicMock, lifespan_app: FastAPI
) -> None:
    """app.state.skill_registry is populated with builtin skills after lifespan starts."""
    mock_redis_client = AsyncMock()
    mock_redis_client.ping = AsyncMock(return_value=True)
    mock_redis_client.get = AsyncMock(return_value=None)
    mock_aioredis.from_url.return_value = mock_redis_client
    mock_aioredis.ConnectionError = ConnectionError
    mock_aioredis.TimeoutError = TimeoutError

    mock_pool = AsyncMock()
    mock_asyncpg.create_pool = AsyncMock(return_value=mock_pool)
    mock_asyncpg.PostgresError = Exception
    mock_asyncpg.InterfaceError = Exception

    async with lifespan(lifespan_app):
        registry = lifespan_app.state.skill_registry
        assert registry is not None
        assert len(registry.list_skills()) > 0


@pytest.mark.asyncio
@patch("silkroute.api.app.asyncpg")
@patch("silkroute.api.app.aioredis")
async def test_cleanup_redis_aclose(
    mock_aioredis: MagicMock, mock_asyncpg: MagicMock, lifespan_app: FastAPI
) -> None:
    """redis.aclose() is called after the lifespan context exits."""
    mock_redis_client = AsyncMock()
    mock_redis_client.ping = AsyncMock(return_value=True)
    mock_redis_client.get = AsyncMock(return_value=None)
    mock_redis_client.aclose = AsyncMock()
    mock_aioredis.from_url.return_value = mock_redis_client
    mock_aioredis.ConnectionError = ConnectionError
    mock_aioredis.TimeoutError = TimeoutError

    mock_pool = AsyncMock()
    mock_asyncpg.create_pool = AsyncMock(return_value=mock_pool)
    mock_asyncpg.PostgresError = Exception
    mock_asyncpg.InterfaceError = Exception

    async with lifespan(lifespan_app):
        pass  # yield point — cleanup runs after this block

    mock_redis_client.aclose.assert_called_once()


@pytest.mark.asyncio
@patch("silkroute.api.app.asyncpg")
@patch("silkroute.api.app.aioredis")
async def test_cleanup_db_pool_close(
    mock_aioredis: MagicMock, mock_asyncpg: MagicMock, lifespan_app: FastAPI
) -> None:
    """pool.close() is called after the lifespan context exits."""
    mock_redis_client = AsyncMock()
    mock_redis_client.ping = AsyncMock(return_value=True)
    mock_redis_client.get = AsyncMock(return_value=None)
    mock_aioredis.from_url.return_value = mock_redis_client
    mock_aioredis.ConnectionError = ConnectionError
    mock_aioredis.TimeoutError = TimeoutError

    mock_pool = AsyncMock()
    mock_pool.close = AsyncMock()
    mock_asyncpg.create_pool = AsyncMock(return_value=mock_pool)
    mock_asyncpg.PostgresError = Exception
    mock_asyncpg.InterfaceError = Exception

    async with lifespan(lifespan_app):
        pass  # yield point — cleanup runs after this block

    mock_pool.close.assert_called_once()


@pytest.mark.asyncio
@patch("silkroute.api.app.asyncpg")
@patch("silkroute.api.app.aioredis")
async def test_cleanup_when_none(
    mock_aioredis: MagicMock, mock_asyncpg: MagicMock, lifespan_app: FastAPI
) -> None:
    """Cleanup does not raise when redis and db_pool are both None."""
    # Both Redis and Postgres fail to connect
    mock_aioredis.from_url.side_effect = ConnectionError("refused")
    mock_aioredis.ConnectionError = ConnectionError
    mock_aioredis.TimeoutError = TimeoutError

    mock_asyncpg.create_pool = AsyncMock(side_effect=OSError("refused"))
    mock_asyncpg.PostgresError = Exception
    mock_asyncpg.InterfaceError = Exception

    # Should complete without raising during cleanup
    async with lifespan(lifespan_app):
        assert lifespan_app.state.redis is None
        assert lifespan_app.state.db_pool is None
