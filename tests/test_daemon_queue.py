"""Tests for daemon task queue — submit, consume, drain, result tracking.

Uses fakeredis for Redis-backed TaskQueue testing without a real server.
"""

from __future__ import annotations

from datetime import UTC, datetime

import fakeredis.aioredis
import pytest

from silkroute.daemon.queue import TaskQueue, TaskRequest, TaskResult


class TestTaskRequest:
    """TaskRequest dataclass tests."""

    def test_defaults(self) -> None:
        req = TaskRequest(task="review code")
        assert req.task == "review code"
        assert req.project_id == "default"
        assert req.model_override is None
        assert req.tier_override is None
        assert req.max_iterations == 25
        assert req.budget_limit_usd == 10.0
        assert req.priority == 0
        assert isinstance(req.id, str)
        assert len(req.id) == 36  # UUID format
        assert isinstance(req.submitted_at, datetime)

    def test_custom_fields(self) -> None:
        req = TaskRequest(
            task="complex analysis",
            project_id="myproject",
            model_override="deepseek/deepseek-r1-0528",
            tier_override="premium",
            max_iterations=50,
            budget_limit_usd=25.0,
            priority=5,
        )
        assert req.project_id == "myproject"
        assert req.model_override == "deepseek/deepseek-r1-0528"
        assert req.tier_override == "premium"
        assert req.max_iterations == 50
        assert req.budget_limit_usd == 25.0
        assert req.priority == 5

    def test_unique_ids(self) -> None:
        r1 = TaskRequest(task="a")
        r2 = TaskRequest(task="b")
        assert r1.id != r2.id

    def test_submitted_at_uses_utc(self) -> None:
        req = TaskRequest(task="test")
        assert req.submitted_at.tzinfo is UTC


class TestTaskResult:
    """TaskResult dataclass tests."""

    def test_success_result(self) -> None:
        result = TaskResult(
            request_id="abc-123",
            session_id="sess-456",
            status="completed",
            cost_usd=0.05,
            iterations=3,
            duration_ms=12000,
        )
        assert result.status == "completed"
        assert result.error is None

    def test_failure_result(self) -> None:
        result = TaskResult(
            request_id="abc-123",
            session_id="sess-456",
            status="failed",
            cost_usd=0.01,
            iterations=1,
            duration_ms=500,
            error="LLM API timeout",
        )
        assert result.status == "failed"
        assert result.error == "LLM API timeout"


class TestTaskQueue:
    """TaskQueue async tests with fakeredis."""

    @pytest.mark.asyncio
    async def test_submit_and_consume(self, fake_redis: fakeredis.aioredis.FakeRedis) -> None:
        q = TaskQueue(redis=fake_redis)
        req = TaskRequest(task="hello")
        rid = await q.submit(req)
        assert rid == req.id
        assert await q.pending_count() == 1

        consumed = await q.consume()
        assert consumed.id == req.id
        assert consumed.task == "hello"
        assert await q.pending_count() == 0

    @pytest.mark.asyncio
    async def test_fifo_ordering(self, fake_redis: fakeredis.aioredis.FakeRedis) -> None:
        q = TaskQueue(redis=fake_redis)
        r1 = TaskRequest(task="first")
        r2 = TaskRequest(task="second")
        r3 = TaskRequest(task="third")
        await q.submit(r1)
        await q.submit(r2)
        await q.submit(r3)

        assert (await q.consume()).task == "first"
        assert (await q.consume()).task == "second"
        assert (await q.consume()).task == "third"

    @pytest.mark.asyncio
    async def test_consume_returns_none_on_timeout(
        self, fake_redis: fakeredis.aioredis.FakeRedis
    ) -> None:
        q = TaskQueue(redis=fake_redis)
        result = await q.consume(timeout=0.1)
        assert result is None

    @pytest.mark.asyncio
    async def test_consume_returns_task_when_available(
        self, fake_redis: fakeredis.aioredis.FakeRedis
    ) -> None:
        q = TaskQueue(redis=fake_redis)
        await q.submit(TaskRequest(task="ready"))
        result = await q.consume(timeout=1.0)
        assert result is not None
        assert result.task == "ready"

    @pytest.mark.asyncio
    async def test_record_and_get_result(self, fake_redis: fakeredis.aioredis.FakeRedis) -> None:
        q = TaskQueue(redis=fake_redis)
        result = TaskResult(
            request_id="req-1",
            session_id="sess-1",
            status="completed",
            cost_usd=0.02,
            iterations=2,
            duration_ms=5000,
        )
        await q.record_result(result)
        got = await q.get_result("req-1")
        assert got is not None
        assert got.request_id == result.request_id
        assert got.status == result.status
        assert await q.get_result("nonexistent") is None

    @pytest.mark.asyncio
    async def test_get_result_returns_latest(
        self, fake_redis: fakeredis.aioredis.FakeRedis
    ) -> None:
        q = TaskQueue(redis=fake_redis)
        r1 = TaskResult(
            request_id="req-1", session_id="s1", status="failed",
            cost_usd=0.01, iterations=1, duration_ms=100, error="boom",
        )
        r2 = TaskResult(
            request_id="req-1", session_id="s2", status="completed",
            cost_usd=0.03, iterations=3, duration_ms=9000,
        )
        await q.record_result(r1)
        await q.record_result(r2)
        got = await q.get_result("req-1")
        assert got is not None
        assert got.status == "completed"
        assert got.session_id == "s2"

    @pytest.mark.asyncio
    async def test_drain(self, fake_redis: fakeredis.aioredis.FakeRedis) -> None:
        q = TaskQueue(redis=fake_redis)
        await q.submit(TaskRequest(task="a"))
        await q.submit(TaskRequest(task="b"))
        await q.submit(TaskRequest(task="c"))
        assert await q.pending_count() == 3

        drained = await q.drain()
        assert len(drained) == 3
        assert await q.pending_count() == 0
        assert [d.task for d in drained] == ["a", "b", "c"]

    @pytest.mark.asyncio
    async def test_drain_empty_queue(self, fake_redis: fakeredis.aioredis.FakeRedis) -> None:
        q = TaskQueue(redis=fake_redis)
        drained = await q.drain()
        assert drained == []

    @pytest.mark.asyncio
    async def test_total_submitted_counter(
        self, fake_redis: fakeredis.aioredis.FakeRedis
    ) -> None:
        q = TaskQueue(redis=fake_redis)
        assert q.total_submitted == 0
        await q.submit(TaskRequest(task="a"))
        await q.submit(TaskRequest(task="b"))
        assert q.total_submitted == 2

    @pytest.mark.asyncio
    async def test_total_completed_counter(
        self, fake_redis: fakeredis.aioredis.FakeRedis
    ) -> None:
        q = TaskQueue(redis=fake_redis)
        assert q.total_completed == 0
        await q.record_result(TaskResult(
            request_id="r1", session_id="s1", status="completed",
            cost_usd=0.01, iterations=1, duration_ms=100,
        ))
        await q.record_result(TaskResult(
            request_id="r2", session_id="s2", status="failed",
            cost_usd=0.02, iterations=2, duration_ms=200,
        ))
        assert q.total_completed == 2

    @pytest.mark.asyncio
    async def test_maxsize_backpressure(self, fake_redis: fakeredis.aioredis.FakeRedis) -> None:
        q = TaskQueue(redis=fake_redis, maxsize=2)
        await q.submit(TaskRequest(task="a"))
        await q.submit(TaskRequest(task="b"))
        # Third submit should raise — queue full
        with pytest.raises(RuntimeError, match="Queue full"):
            await q.submit(TaskRequest(task="c"))

    @pytest.mark.asyncio
    async def test_init_counters_from_redis(
        self, fake_redis: fakeredis.aioredis.FakeRedis
    ) -> None:
        """Counters should initialize from Redis values (crash recovery)."""
        await fake_redis.set("silkroute:counter:submitted", "42")
        await fake_redis.set("silkroute:counter:completed", "37")

        q = TaskQueue(redis=fake_redis)
        await q.init_counters()
        assert q.total_submitted == 42
        assert q.total_completed == 37

    @pytest.mark.asyncio
    async def test_init_counters_defaults_to_zero(
        self, fake_redis: fakeredis.aioredis.FakeRedis
    ) -> None:
        """Counters should default to 0 when Redis has no values."""
        q = TaskQueue(redis=fake_redis)
        await q.init_counters()
        assert q.total_submitted == 0
        assert q.total_completed == 0

    @pytest.mark.asyncio
    async def test_counters_persist_in_redis(
        self, fake_redis: fakeredis.aioredis.FakeRedis
    ) -> None:
        """Submit and record_result should INCR Redis counters."""
        q = TaskQueue(redis=fake_redis)
        await q.submit(TaskRequest(task="a"))
        await q.record_result(TaskResult(
            request_id="r1", session_id="s1", status="completed",
            cost_usd=0.01, iterations=1, duration_ms=100,
        ))

        assert await fake_redis.get("silkroute:counter:submitted") == "1"
        assert await fake_redis.get("silkroute:counter:completed") == "1"

    @pytest.mark.asyncio
    async def test_submit_preserves_all_fields(
        self, fake_redis: fakeredis.aioredis.FakeRedis
    ) -> None:
        """All TaskRequest fields should survive the Redis round-trip."""
        q = TaskQueue(redis=fake_redis)
        original = TaskRequest(
            task="complex task",
            project_id="proj-1",
            model_override="deepseek/deepseek-r1-0528",
            tier_override="premium",
            max_iterations=50,
            budget_limit_usd=25.0,
            priority=5,
        )
        await q.submit(original)
        consumed = await q.consume()

        assert consumed.task == original.task
        assert consumed.id == original.id
        assert consumed.project_id == original.project_id
        assert consumed.model_override == original.model_override
        assert consumed.tier_override == original.tier_override
        assert consumed.max_iterations == original.max_iterations
        assert consumed.budget_limit_usd == original.budget_limit_usd
        assert consumed.priority == original.priority
