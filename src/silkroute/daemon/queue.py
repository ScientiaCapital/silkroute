"""Task queue for daemon mode — submit, consume, and track agent tasks.

Uses asyncio.Queue for backpressure-aware, concurrent-safe task management.
TaskRequest and TaskResult are lightweight dataclasses for serialization.
"""

from __future__ import annotations

import asyncio
import uuid
from dataclasses import dataclass, field
from datetime import UTC, datetime


@dataclass
class TaskRequest:
    """A task submitted to the daemon for agent execution."""

    task: str
    id: str = field(default_factory=lambda: str(uuid.uuid4()))
    project_id: str = "default"
    model_override: str | None = None
    tier_override: str | None = None
    max_iterations: int = 25
    budget_limit_usd: float = 10.0
    priority: int = 0
    submitted_at: datetime = field(default_factory=lambda: datetime.now(UTC))


@dataclass
class TaskResult:
    """Outcome of a completed agent task."""

    request_id: str
    session_id: str
    status: str  # completed / failed / timeout / budget_exceeded
    cost_usd: float
    iterations: int
    duration_ms: int
    error: str | None = None


class TaskQueue:
    """Async queue for daemon task management.

    Wraps asyncio.Queue with result tracking and graceful drain support.
    maxsize controls backpressure — submit() blocks when queue is full.
    """

    def __init__(self, maxsize: int = 100) -> None:
        self._queue: asyncio.Queue[TaskRequest] = asyncio.Queue(maxsize=maxsize)
        self._results: dict[str, TaskResult] = {}
        self._total_submitted: int = 0
        self._total_completed: int = 0

    async def submit(self, request: TaskRequest) -> str:
        """Enqueue a task request. Returns the request ID.

        Blocks if the queue is full (backpressure).
        """
        await self._queue.put(request)
        self._total_submitted += 1
        return request.id

    async def consume(self) -> TaskRequest:
        """Dequeue the next task. Blocks until one is available."""
        return await self._queue.get()

    def record_result(self, result: TaskResult) -> None:
        """Store a completed task result for later retrieval."""
        self._results[result.request_id] = result
        self._total_completed += 1

    def get_result(self, request_id: str) -> TaskResult | None:
        """Look up a result by request ID. Returns None if not found."""
        return self._results.get(request_id)

    def pending_count(self) -> int:
        """Number of tasks waiting in the queue."""
        return self._queue.qsize()

    @property
    def total_submitted(self) -> int:
        """Total tasks ever submitted."""
        return self._total_submitted

    @property
    def total_completed(self) -> int:
        """Total tasks that have recorded results."""
        return self._total_completed

    async def drain(self) -> list[TaskRequest]:
        """Remove all pending tasks from the queue (for shutdown).

        Returns the drained tasks so they can be logged.
        """
        drained: list[TaskRequest] = []
        while not self._queue.empty():
            try:
                drained.append(self._queue.get_nowait())
            except asyncio.QueueEmpty:
                break
        return drained
