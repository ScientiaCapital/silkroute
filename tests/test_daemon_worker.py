"""Tests for daemon worker — task execution, error handling, shutdown."""

from __future__ import annotations

import asyncio
from unittest.mock import AsyncMock, MagicMock, patch

import fakeredis.aioredis
import pytest

from silkroute.daemon.queue import TaskQueue, TaskRequest, TaskResult
from silkroute.daemon.worker import execute_task, worker_loop


def _make_mock_session(
    *,
    session_id: str = "sess-123",
    status: str = "completed",
    cost_usd: float = 0.05,
    iteration_count: int = 3,
) -> object:
    """Create a mock AgentSession for testing."""
    session = MagicMock()
    session.id = session_id
    session.status.value = status
    session.total_cost_usd = cost_usd
    session.iteration_count = iteration_count
    return session


class TestExecuteTask:
    """execute_task() tests."""

    @pytest.mark.asyncio
    async def test_success(self) -> None:
        request = TaskRequest(task="write tests")
        mock_session = _make_mock_session()

        with patch("silkroute.agent.run_agent", new_callable=AsyncMock) as mock_run:
            mock_run.return_value = mock_session
            result = await execute_task(request)

        assert isinstance(result, TaskResult)
        assert result.request_id == request.id
        assert result.session_id == "sess-123"
        assert result.status == "completed"
        assert result.cost_usd == 0.05
        assert result.iterations == 3
        assert result.duration_ms >= 0
        assert result.error is None

    @pytest.mark.asyncio
    async def test_passes_request_params_to_run_agent(self) -> None:
        request = TaskRequest(
            task="analyze code",
            model_override="deepseek/deepseek-r1-0528",
            tier_override="premium",
            project_id="myproject",
            max_iterations=50,
            budget_limit_usd=25.0,
        )
        mock_session = _make_mock_session()

        with patch("silkroute.agent.run_agent", new_callable=AsyncMock) as mock_run:
            mock_run.return_value = mock_session
            await execute_task(request)

        mock_run.assert_called_once_with(
            "analyze code",
            model_override="deepseek/deepseek-r1-0528",
            tier_override="premium",
            project_id="myproject",
            max_iterations=50,
            budget_limit_usd=25.0,
            daemon_mode=True,
        )

    @pytest.mark.asyncio
    async def test_handles_run_agent_exception(self) -> None:
        request = TaskRequest(task="bad task")

        with patch("silkroute.agent.run_agent", new_callable=AsyncMock) as mock_run:
            mock_run.side_effect = RuntimeError("LLM API timeout")
            result = await execute_task(request)

        assert result.status == "failed"
        assert result.error == "LLM API timeout"
        assert result.session_id == ""
        assert result.cost_usd == 0.0
        assert result.iterations == 0


class TestWorkerLoop:
    """worker_loop() tests."""

    @pytest.mark.asyncio
    async def test_consumes_and_processes_task(
        self, fake_redis: fakeredis.aioredis.FakeRedis
    ) -> None:
        q = TaskQueue(redis=fake_redis)
        shutdown = asyncio.Event()
        req = TaskRequest(task="test task")
        await q.submit(req)

        mock_session = _make_mock_session()

        with patch("silkroute.agent.run_agent", new_callable=AsyncMock) as mock_run:
            mock_run.return_value = mock_session

            # Set shutdown after processing
            async def shutdown_after_delay() -> None:
                await asyncio.sleep(0.1)
                shutdown.set()

            asyncio.create_task(shutdown_after_delay())
            await worker_loop(worker_id=1, queue=q, shutdown_event=shutdown)

        assert q.total_completed == 1
        result = await q.get_result(req.id)
        assert result is not None
        assert result.status == "completed"

    @pytest.mark.asyncio
    async def test_stops_on_shutdown_event(
        self, fake_redis: fakeredis.aioredis.FakeRedis
    ) -> None:
        q = TaskQueue(redis=fake_redis)
        shutdown = asyncio.Event()
        shutdown.set()  # Already set — worker should exit immediately

        with patch("silkroute.agent.run_agent", new_callable=AsyncMock):
            await asyncio.wait_for(
                worker_loop(worker_id=1, queue=q, shutdown_event=shutdown),
                timeout=2.0,
            )

    @pytest.mark.asyncio
    async def test_handles_task_failure_gracefully(
        self, fake_redis: fakeredis.aioredis.FakeRedis
    ) -> None:
        q = TaskQueue(redis=fake_redis)
        shutdown = asyncio.Event()
        req = TaskRequest(task="failing task")
        await q.submit(req)

        with patch("silkroute.agent.run_agent", new_callable=AsyncMock) as mock_run:
            mock_run.side_effect = RuntimeError("boom")

            async def shutdown_after_delay() -> None:
                await asyncio.sleep(0.1)
                shutdown.set()

            asyncio.create_task(shutdown_after_delay())
            # Should not raise — failure is recorded as a result
            await worker_loop(worker_id=1, queue=q, shutdown_event=shutdown)

        result = await q.get_result(req.id)
        assert result is not None
        assert result.status == "failed"
        assert result.error == "boom"

    @pytest.mark.asyncio
    async def test_processes_multiple_tasks(
        self, fake_redis: fakeredis.aioredis.FakeRedis
    ) -> None:
        q = TaskQueue(redis=fake_redis)
        shutdown = asyncio.Event()
        r1 = TaskRequest(task="task 1")
        r2 = TaskRequest(task="task 2")
        await q.submit(r1)
        await q.submit(r2)

        mock_session = _make_mock_session()

        with patch("silkroute.agent.run_agent", new_callable=AsyncMock) as mock_run:
            mock_run.return_value = mock_session

            async def shutdown_after_delay() -> None:
                await asyncio.sleep(0.2)
                shutdown.set()

            asyncio.create_task(shutdown_after_delay())
            await worker_loop(worker_id=1, queue=q, shutdown_event=shutdown)

        assert q.total_completed == 2
        assert await q.get_result(r1.id) is not None
        assert await q.get_result(r2.id) is not None
