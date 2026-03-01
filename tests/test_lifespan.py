"""Tests for the lifespan context manager in silkroute.api.app.

Tests the full startup/teardown lifecycle for Redis, Postgres, and
SkillRegistry without requiring real infrastructure.
"""

from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from fastapi import FastAPI

from silkroute.api.app import lifespan
from silkroute.config.settings import (
    ApiConfig,
    DatabaseConfig,
    ProviderConfig,
    SilkRouteSettings,
)
from silkroute.daemon.queue import TaskQueue


def _make_settings() -> SilkRouteSettings:
    return SilkRouteSettings(
        providers=ProviderConfig(ollama_enabled=True),
        api=ApiConfig(api_key="test-secret"),
        database=DatabaseConfig(
            redis_url="redis://localhost:6379/0",
            postgres_url="postgresql://silkroute:silkroute@localhost:5432/silkroute",
        ),
    )


def _make_app() -> FastAPI:
    """Create a minimal FastAPI app with settings pre-attached."""
    app = FastAPI()
    app.state.settings = _make_settings()
    return app


@pytest.mark.asyncio
@patch("silkroute.api.app.asyncpg")
@patch("silkroute.api.app.aioredis")
async def test_redis_connect_success(mock_aioredis: MagicMock, mock_asyncpg: MagicMock) -> None:
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

    app = _make_app()

    async with lifespan(app):
        assert app.state.redis is mock_redis_client
        assert isinstance(app.state.queue, TaskQueue)


@pytest.mark.asyncio
@patch("silkroute.api.app.asyncpg")
@patch("silkroute.api.app.aioredis")
async def test_redis_connect_failure(mock_aioredis: MagicMock, mock_asyncpg: MagicMock) -> None:
    """app.state.redis and app.state.queue are None when Redis raises ConnectionError."""
    mock_aioredis.from_url.side_effect = ConnectionError("refused")
    mock_aioredis.ConnectionError = ConnectionError
    mock_aioredis.TimeoutError = TimeoutError

    mock_pool = AsyncMock()
    mock_asyncpg.create_pool = AsyncMock(return_value=mock_pool)
    mock_asyncpg.PostgresError = Exception
    mock_asyncpg.InterfaceError = Exception

    app = _make_app()

    async with lifespan(app):
        assert app.state.redis is None
        assert app.state.queue is None


@pytest.mark.asyncio
@patch("silkroute.api.app.asyncpg")
@patch("silkroute.api.app.aioredis")
async def test_postgres_connect_success(mock_aioredis: MagicMock, mock_asyncpg: MagicMock) -> None:
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

    app = _make_app()

    async with lifespan(app):
        assert app.state.db_pool is mock_pool


@pytest.mark.asyncio
@patch("silkroute.api.app.asyncpg")
@patch("silkroute.api.app.aioredis")
async def test_postgres_connect_failure(mock_aioredis: MagicMock, mock_asyncpg: MagicMock) -> None:
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

    app = _make_app()

    async with lifespan(app):
        assert app.state.db_pool is None


@pytest.mark.asyncio
@patch("silkroute.api.app.asyncpg")
@patch("silkroute.api.app.aioredis")
async def test_skill_registry_initialized(
    mock_aioredis: MagicMock, mock_asyncpg: MagicMock
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

    app = _make_app()

    async with lifespan(app):
        registry = app.state.skill_registry
        assert registry is not None
        assert len(registry.list_skills()) > 0


@pytest.mark.asyncio
@patch("silkroute.api.app.asyncpg")
@patch("silkroute.api.app.aioredis")
async def test_cleanup_redis_aclose(mock_aioredis: MagicMock, mock_asyncpg: MagicMock) -> None:
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

    app = _make_app()

    async with lifespan(app):
        pass  # yield point — cleanup runs after this block

    mock_redis_client.aclose.assert_called_once()


@pytest.mark.asyncio
@patch("silkroute.api.app.asyncpg")
@patch("silkroute.api.app.aioredis")
async def test_cleanup_db_pool_close(mock_aioredis: MagicMock, mock_asyncpg: MagicMock) -> None:
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

    app = _make_app()

    async with lifespan(app):
        pass  # yield point — cleanup runs after this block

    mock_pool.close.assert_called_once()


@pytest.mark.asyncio
@patch("silkroute.api.app.asyncpg")
@patch("silkroute.api.app.aioredis")
async def test_cleanup_when_none(mock_aioredis: MagicMock, mock_asyncpg: MagicMock) -> None:
    """Cleanup does not raise when redis and db_pool are both None."""
    # Both Redis and Postgres fail to connect
    mock_aioredis.from_url.side_effect = ConnectionError("refused")
    mock_aioredis.ConnectionError = ConnectionError
    mock_aioredis.TimeoutError = TimeoutError

    mock_asyncpg.create_pool = AsyncMock(side_effect=OSError("refused"))
    mock_asyncpg.PostgresError = Exception
    mock_asyncpg.InterfaceError = Exception

    app = _make_app()

    # Should complete without raising during cleanup
    async with lifespan(app):
        assert app.state.redis is None
        assert app.state.db_pool is None
