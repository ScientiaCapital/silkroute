"""Tests for daemon heartbeat ticker — lifecycle, emission, interval timing."""

from __future__ import annotations

import asyncio
from unittest.mock import patch

import fakeredis.aioredis
import pytest

from silkroute.daemon.heartbeat import HeartbeatTicker
from silkroute.daemon.queue import TaskQueue


class TestHeartbeatTicker:
    """HeartbeatTicker lifecycle and emission tests."""

    @pytest.mark.asyncio
    async def test_start_creates_task(self, fake_redis: fakeredis.aioredis.FakeRedis) -> None:
        q = TaskQueue(redis=fake_redis)
        ticker = HeartbeatTicker(interval=60, queue=q)
        ticker.start()
        assert ticker.is_running
        await ticker.stop()
        assert not ticker.is_running

    @pytest.mark.asyncio
    async def test_stop_is_idempotent(self, fake_redis: fakeredis.aioredis.FakeRedis) -> None:
        q = TaskQueue(redis=fake_redis)
        ticker = HeartbeatTicker(interval=60, queue=q)
        ticker.start()
        await ticker.stop()
        await ticker.stop()  # Second stop should not raise
        assert not ticker.is_running

    @pytest.mark.asyncio
    async def test_stop_without_start(self, fake_redis: fakeredis.aioredis.FakeRedis) -> None:
        q = TaskQueue(redis=fake_redis)
        ticker = HeartbeatTicker(interval=60, queue=q)
        await ticker.stop()  # Should not raise

    @pytest.mark.asyncio
    async def test_heartbeat_emits_log(self, fake_redis: fakeredis.aioredis.FakeRedis) -> None:
        q = TaskQueue(redis=fake_redis)
        ticker = HeartbeatTicker(interval=0.05, queue=q)

        with patch("silkroute.daemon.heartbeat.log") as mock_log:
            ticker.start()
            await asyncio.sleep(0.15)  # Should get ~2-3 heartbeats
            await ticker.stop()

        # Filter for heartbeat calls (not start/stop)
        heartbeat_calls = [
            c for c in mock_log.info.call_args_list
            if c.args and c.args[0] == "heartbeat"
        ]
        assert len(heartbeat_calls) >= 1

    @pytest.mark.asyncio
    async def test_heartbeat_includes_queue_metrics(
        self, fake_redis: fakeredis.aioredis.FakeRedis
    ) -> None:
        q = TaskQueue(redis=fake_redis)
        ticker = HeartbeatTicker(interval=0.05, queue=q)

        with patch("silkroute.daemon.heartbeat.log") as mock_log:
            ticker.start()
            await asyncio.sleep(0.1)
            await ticker.stop()

        heartbeat_calls = [
            c for c in mock_log.info.call_args_list
            if c.args and c.args[0] == "heartbeat"
        ]
        assert len(heartbeat_calls) >= 1

        kwargs = heartbeat_calls[0].kwargs
        assert "uptime_seconds" in kwargs
        assert "queue_pending" in kwargs
        assert "queue_total_submitted" in kwargs
        assert "queue_total_completed" in kwargs
        assert "active_workers" in kwargs
        assert "rss_mb" in kwargs

    @pytest.mark.asyncio
    async def test_active_workers_fn_called(
        self, fake_redis: fakeredis.aioredis.FakeRedis
    ) -> None:
        q = TaskQueue(redis=fake_redis)
        ticker = HeartbeatTicker(
            interval=0.05,
            queue=q,
            active_workers_fn=lambda: 2,
        )

        with patch("silkroute.daemon.heartbeat.log") as mock_log:
            ticker.start()
            await asyncio.sleep(0.1)
            await ticker.stop()

        heartbeat_calls = [
            c for c in mock_log.info.call_args_list
            if c.args and c.args[0] == "heartbeat"
        ]
        assert len(heartbeat_calls) >= 1
        assert heartbeat_calls[0].kwargs["active_workers"] == 2

    @pytest.mark.asyncio
    async def test_is_running_reflects_task_state(
        self, fake_redis: fakeredis.aioredis.FakeRedis
    ) -> None:
        q = TaskQueue(redis=fake_redis)
        ticker = HeartbeatTicker(interval=60, queue=q)
        assert not ticker.is_running
        ticker.start()
        assert ticker.is_running
        await ticker.stop()
        assert not ticker.is_running
