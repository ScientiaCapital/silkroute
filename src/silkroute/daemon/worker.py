"""Worker coroutine — consumes tasks from the queue and runs the agent loop.

Each worker is an asyncio task that loops: consume request → run_agent() → record result.
Respects a shutdown event for graceful termination.
"""

from __future__ import annotations

import asyncio
import time

import structlog

from silkroute.daemon.queue import TaskQueue, TaskRequest, TaskResult

log = structlog.get_logger()


async def worker_loop(
    worker_id: int,
    queue: TaskQueue,
    shutdown_event: asyncio.Event,
) -> None:
    """Consume tasks from queue and run agent. Loops until shutdown.

    Uses a 1-second timeout on consume() to periodically check the shutdown
    event, enabling graceful shutdown even when the queue is empty.
    """

    log.info("worker_started", worker_id=worker_id)

    while not shutdown_event.is_set():
        try:
            request = await asyncio.wait_for(queue.consume(), timeout=1.0)
        except TimeoutError:
            continue  # Check shutdown_event again

        log.info(
            "worker_task_started",
            worker_id=worker_id,
            request_id=request.id,
            task=request.task[:100],
        )

        result = await execute_task(request)
        queue.record_result(result)

        log.info(
            "worker_task_completed",
            worker_id=worker_id,
            request_id=request.id,
            status=result.status,
            cost_usd=result.cost_usd,
            duration_ms=result.duration_ms,
        )

    log.info("worker_stopped", worker_id=worker_id)


async def execute_task(request: TaskRequest) -> TaskResult:
    """Run a single task through the agent loop and return a TaskResult.

    Wraps run_agent() with error handling and maps AgentSession → TaskResult.
    """
    start_ms = int(time.monotonic() * 1000)

    try:
        from silkroute.agent import run_agent

        session = await run_agent(
            request.task,
            model_override=request.model_override,
            tier_override=request.tier_override,
            project_id=request.project_id,
            max_iterations=request.max_iterations,
            budget_limit_usd=request.budget_limit_usd,
            daemon_mode=True,
        )

        duration_ms = int(time.monotonic() * 1000) - start_ms

        return TaskResult(
            request_id=request.id,
            session_id=session.id,
            status=session.status.value,
            cost_usd=session.total_cost_usd,
            iterations=session.iteration_count,
            duration_ms=duration_ms,
        )

    except Exception as exc:
        duration_ms = int(time.monotonic() * 1000) - start_ms
        log.error(
            "execute_task_failed",
            request_id=request.id,
            error=str(exc),
        )
        return TaskResult(
            request_id=request.id,
            session_id="",
            status="failed",
            cost_usd=0.0,
            iterations=0,
            duration_ms=duration_ms,
            error=str(exc),
        )
