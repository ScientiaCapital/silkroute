"""Tests for daemon Redis pool singleton — lifecycle, retry, URL masking."""

from __future__ import annotations

import asyncio
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from silkroute.daemon.redis_pool import (
    _mask_redis_url,
    close_redis,
    get_redis,
    redis_retry,
)


class TestGetRedis:
    """get_redis() singleton tests."""

    @pytest.mark.asyncio
    async def test_returns_client_on_success(self) -> None:
        mock_client = AsyncMock()
        mock_client.ping = AsyncMock()

        with (
            patch("silkroute.daemon.redis_pool._redis", None),
            patch("silkroute.daemon.redis_pool._redis_lock", asyncio.Lock()),
            patch("silkroute.daemon.redis_pool.aioredis") as mock_aioredis,
        ):
            mock_aioredis.from_url.return_value = mock_client
            mock_aioredis.ConnectionError = ConnectionError
            mock_aioredis.TimeoutError = TimeoutError

            result = await get_redis()

        assert result is mock_client
        mock_client.ping.assert_awaited_once()

    @pytest.mark.asyncio
    async def test_returns_none_on_connection_failure(self) -> None:
        with (
            patch("silkroute.daemon.redis_pool._redis", None),
            patch("silkroute.daemon.redis_pool._redis_lock", asyncio.Lock()),
            patch("silkroute.daemon.redis_pool.aioredis") as mock_aioredis,
        ):
            mock_aioredis.from_url.side_effect = OSError("Connection refused")
            mock_aioredis.ConnectionError = ConnectionError
            mock_aioredis.TimeoutError = TimeoutError

            result = await get_redis()

        assert result is None

    @pytest.mark.asyncio
    async def test_returns_cached_client(self) -> None:
        mock_client = AsyncMock()

        with patch("silkroute.daemon.redis_pool._redis", mock_client):
            result = await get_redis()

        assert result is mock_client


class TestCloseRedis:
    """close_redis() tests."""

    @pytest.mark.asyncio
    async def test_closes_existing_client(self) -> None:
        mock_client = AsyncMock()
        mock_client.aclose = AsyncMock()

        with patch("silkroute.daemon.redis_pool._redis", mock_client):
            await close_redis()

        mock_client.aclose.assert_awaited_once()

    @pytest.mark.asyncio
    async def test_noop_when_no_client(self) -> None:
        with patch("silkroute.daemon.redis_pool._redis", None):
            await close_redis()  # Should not raise


class TestRedisRetry:
    """redis_retry decorator tests."""

    @pytest.mark.asyncio
    async def test_succeeds_on_first_try(self) -> None:
        call_count = 0

        @redis_retry
        async def good_fn() -> str:
            nonlocal call_count
            call_count += 1
            return "ok"

        result = await good_fn()
        assert result == "ok"
        assert call_count == 1

    @pytest.mark.asyncio
    async def test_retries_on_connection_error(self) -> None:
        import redis.asyncio as aioredis

        call_count = 0

        @redis_retry
        async def flaky_fn() -> str:
            nonlocal call_count
            call_count += 1
            if call_count < 3:
                raise aioredis.ConnectionError("gone")
            return "recovered"

        with patch("silkroute.daemon.redis_pool.asyncio.sleep", new_callable=AsyncMock):
            result = await flaky_fn()

        assert result == "recovered"
        assert call_count == 3

    @pytest.mark.asyncio
    async def test_raises_after_max_retries(self) -> None:
        import redis.asyncio as aioredis

        @redis_retry
        async def always_fails() -> str:
            raise aioredis.ConnectionError("permanent failure")

        with (
            patch("silkroute.daemon.redis_pool.asyncio.sleep", new_callable=AsyncMock),
            pytest.raises(aioredis.ConnectionError, match="permanent failure"),
        ):
            await always_fails()


class TestMaskRedisUrl:
    """_mask_redis_url() tests."""

    def test_masks_password(self) -> None:
        url = "redis://:mypassword@localhost:6379/0"
        assert _mask_redis_url(url) == "redis://:***@localhost:6379/0"

    def test_masks_user_password(self) -> None:
        url = "redis://user:pass@host:6379/0"
        assert _mask_redis_url(url) == "redis://user:***@host:6379/0"

    def test_no_mask_without_password(self) -> None:
        url = "redis://localhost:6379/0"
        assert _mask_redis_url(url) == "redis://localhost:6379/0"
