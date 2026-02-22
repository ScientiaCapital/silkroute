"""Tests for daemon task queue — submit, consume, drain, result tracking."""

from __future__ import annotations

import asyncio
from datetime import UTC, datetime

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
    """TaskQueue async tests."""

    @pytest.mark.asyncio
    async def test_submit_and_consume(self) -> None:
        q = TaskQueue()
        req = TaskRequest(task="hello")
        rid = await q.submit(req)
        assert rid == req.id
        assert q.pending_count() == 1

        consumed = await q.consume()
        assert consumed.id == req.id
        assert consumed.task == "hello"
        assert q.pending_count() == 0

    @pytest.mark.asyncio
    async def test_fifo_ordering(self) -> None:
        q = TaskQueue()
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
    async def test_consume_blocks_until_available(self) -> None:
        q = TaskQueue()
        consumed: list[TaskRequest] = []

        async def consumer() -> None:
            consumed.append(await q.consume())

        task = asyncio.create_task(consumer())
        await asyncio.sleep(0.05)
        assert consumed == []  # Still waiting

        await q.submit(TaskRequest(task="delayed"))
        await task
        assert len(consumed) == 1
        assert consumed[0].task == "delayed"

    @pytest.mark.asyncio
    async def test_record_and_get_result(self) -> None:
        q = TaskQueue()
        result = TaskResult(
            request_id="req-1",
            session_id="sess-1",
            status="completed",
            cost_usd=0.02,
            iterations=2,
            duration_ms=5000,
        )
        q.record_result(result)
        assert q.get_result("req-1") is result
        assert q.get_result("nonexistent") is None

    @pytest.mark.asyncio
    async def test_get_result_returns_latest(self) -> None:
        q = TaskQueue()
        r1 = TaskResult(
            request_id="req-1", session_id="s1", status="failed",
            cost_usd=0.01, iterations=1, duration_ms=100, error="boom",
        )
        r2 = TaskResult(
            request_id="req-1", session_id="s2", status="completed",
            cost_usd=0.03, iterations=3, duration_ms=9000,
        )
        q.record_result(r1)
        q.record_result(r2)
        assert q.get_result("req-1") is r2

    @pytest.mark.asyncio
    async def test_drain(self) -> None:
        q = TaskQueue()
        await q.submit(TaskRequest(task="a"))
        await q.submit(TaskRequest(task="b"))
        await q.submit(TaskRequest(task="c"))
        assert q.pending_count() == 3

        drained = await q.drain()
        assert len(drained) == 3
        assert q.pending_count() == 0
        assert [d.task for d in drained] == ["a", "b", "c"]

    @pytest.mark.asyncio
    async def test_drain_empty_queue(self) -> None:
        q = TaskQueue()
        drained = await q.drain()
        assert drained == []

    @pytest.mark.asyncio
    async def test_total_submitted_counter(self) -> None:
        q = TaskQueue()
        assert q.total_submitted == 0
        await q.submit(TaskRequest(task="a"))
        await q.submit(TaskRequest(task="b"))
        assert q.total_submitted == 2

    @pytest.mark.asyncio
    async def test_total_completed_counter(self) -> None:
        q = TaskQueue()
        assert q.total_completed == 0
        q.record_result(TaskResult(
            request_id="r1", session_id="s1", status="completed",
            cost_usd=0.01, iterations=1, duration_ms=100,
        ))
        q.record_result(TaskResult(
            request_id="r2", session_id="s2", status="failed",
            cost_usd=0.02, iterations=2, duration_ms=200,
        ))
        assert q.total_completed == 2

    @pytest.mark.asyncio
    async def test_maxsize_backpressure(self) -> None:
        q = TaskQueue(maxsize=2)
        await q.submit(TaskRequest(task="a"))
        await q.submit(TaskRequest(task="b"))
        # Third submit should block
        blocked = False

        async def try_submit() -> None:
            nonlocal blocked
            blocked = True
            await q.submit(TaskRequest(task="c"))
            blocked = False

        task = asyncio.create_task(try_submit())
        await asyncio.sleep(0.05)
        assert blocked  # Still waiting — queue full

        await q.consume()  # Free up space
        await asyncio.sleep(0.05)
        assert not blocked  # Submit completed
        await task
        assert q.pending_count() == 2  # b + c remain
