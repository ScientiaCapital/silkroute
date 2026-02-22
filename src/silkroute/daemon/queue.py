"""Task queue for daemon mode — submit, consume, and track agent tasks.

Uses Redis for durable, crash-safe task management:
- LIST (silkroute:queue:pending) for FIFO queue with RPUSH/BLPOP
- HASH (silkroute:results) for result storage by request ID
- STRING counters for submitted/completed tracking

TaskRequest and TaskResult are lightweight dataclasses for serialization.
"""

from __future__ import annotations

import uuid
from dataclasses import dataclass, field
from datetime import UTC, datetime

import redis.asyncio as aioredis
import structlog

log = structlog.get_logger()

# Redis key constants
KEY_PENDING = "silkroute:queue:pending"
KEY_RESULTS = "silkroute:results"
KEY_COUNTER_SUBMITTED = "silkroute:counter:submitted"
KEY_COUNTER_COMPLETED = "silkroute:counter:completed"


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
    """Redis-backed async queue for daemon task management.

    Uses Redis LIST for FIFO ordering with RPUSH/BLPOP, HASH for result
    storage, and STRING counters for submit/complete tracking.
    maxsize controls backpressure — submit() raises if queue exceeds limit.
    """

    def __init__(self, redis: aioredis.Redis, maxsize: int = 100) -> None:
        self._redis = redis
        self._maxsize = maxsize
        self._total_submitted: int = 0
        self._total_completed: int = 0

    async def init_counters(self) -> None:
        """Load counter values from Redis (call once after construction)."""
        submitted = await self._redis.get(KEY_COUNTER_SUBMITTED)
        completed = await self._redis.get(KEY_COUNTER_COMPLETED)
        self._total_submitted = int(submitted) if submitted else 0
        self._total_completed = int(completed) if completed else 0

    async def submit(self, request: TaskRequest) -> str:
        """Enqueue a task request. Returns the request ID.

        Raises RuntimeError if the queue is full (backpressure).
        """
        from silkroute.daemon.serialization import serialize_request

        current_len = await self._redis.llen(KEY_PENDING)
        if current_len >= self._maxsize:
            raise RuntimeError(
                f"Queue full ({current_len}/{self._maxsize}). "
                "Try again later or increase maxsize."
            )

        await self._redis.rpush(KEY_PENDING, serialize_request(request))
        await self._redis.incr(KEY_COUNTER_SUBMITTED)
        self._total_submitted += 1
        return request.id

    async def consume(self, timeout: float = 1.0) -> TaskRequest | None:
        """Dequeue the next task. Returns None if timeout expires.

        Uses BLPOP with a configurable timeout. Returns None when no
        task is available within the timeout window, allowing workers
        to check shutdown events between polls.
        """
        from silkroute.daemon.serialization import deserialize_request

        result = await self._redis.blpop(KEY_PENDING, timeout=timeout)
        if result is None:
            return None
        # BLPOP returns (key, value) tuple
        return deserialize_request(result[1])

    async def record_result(self, result: TaskResult) -> None:
        """Store a completed task result in Redis for later retrieval."""
        from silkroute.daemon.serialization import serialize_result

        await self._redis.hset(KEY_RESULTS, result.request_id, serialize_result(result))
        await self._redis.incr(KEY_COUNTER_COMPLETED)
        self._total_completed += 1

    async def get_result(self, request_id: str) -> TaskResult | None:
        """Look up a result by request ID. Returns None if not found."""
        from silkroute.daemon.serialization import deserialize_result

        data = await self._redis.hget(KEY_RESULTS, request_id)
        if data is None:
            return None
        return deserialize_result(data)

    async def pending_count(self) -> int:
        """Number of tasks waiting in the queue."""
        return await self._redis.llen(KEY_PENDING)

    @property
    def total_submitted(self) -> int:
        """Total tasks ever submitted (local shadow counter)."""
        return self._total_submitted

    @property
    def total_completed(self) -> int:
        """Total tasks that have recorded results (local shadow counter)."""
        return self._total_completed

    async def drain(self) -> list[TaskRequest]:
        """Remove all pending tasks from the queue (for shutdown).

        Returns the drained tasks so they can be logged.
        """
        from silkroute.daemon.serialization import deserialize_request

        items = await self._redis.lrange(KEY_PENDING, 0, -1)
        if items:
            await self._redis.delete(KEY_PENDING)
        return [deserialize_request(item) for item in items]
