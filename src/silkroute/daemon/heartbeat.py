"""Heartbeat ticker — periodic health logging for daemon mode.

Emits structured log messages at a configurable interval with queue depth,
worker activity, memory usage, and uptime information.
"""

from __future__ import annotations

import asyncio
import contextlib
import resource
import time

import structlog

from silkroute.daemon.queue import TaskQueue

log = structlog.get_logger()


class HeartbeatTicker:
    """Periodic health monitor that logs daemon vitals via structlog.

    Designed to be started/stopped alongside the DaemonServer lifecycle.
    """

    def __init__(
        self,
        interval: int,
        queue: TaskQueue,
        *,
        active_workers_fn: callable | None = None,
    ) -> None:
        self._interval = interval
        self._queue = queue
        self._active_workers_fn = active_workers_fn or (lambda: 0)
        self._task: asyncio.Task[None] | None = None
        self._started_at: float = 0.0

    def start(self) -> None:
        """Create the heartbeat asyncio task."""
        self._started_at = time.monotonic()
        self._task = asyncio.create_task(self._tick_loop())
        log.info("heartbeat_started", interval_seconds=self._interval)

    async def stop(self) -> None:
        """Cancel the heartbeat task and wait for clean exit."""
        if self._task is not None:
            self._task.cancel()
            with contextlib.suppress(asyncio.CancelledError):
                await self._task
            self._task = None
            log.info("heartbeat_stopped")

    @property
    def is_running(self) -> bool:
        """Whether the heartbeat loop is active."""
        return self._task is not None and not self._task.done()

    async def _tick_loop(self) -> None:
        """Loop forever, emitting heartbeats at the configured interval."""
        try:
            while True:
                await asyncio.sleep(self._interval)
                await self._emit_heartbeat()
        except asyncio.CancelledError:
            raise  # Let stop() catch it

    async def _emit_heartbeat(self) -> None:
        """Log a single heartbeat with daemon vitals."""
        uptime_seconds = int(time.monotonic() - self._started_at)
        rss_mb = resource.getrusage(resource.RUSAGE_SELF).ru_maxrss / (1024 * 1024)

        log.info(
            "heartbeat",
            uptime_seconds=uptime_seconds,
            queue_pending=await self._queue.pending_count(),
            queue_total_submitted=self._queue.total_submitted,
            queue_total_completed=self._queue.total_completed,
            active_workers=self._active_workers_fn(),
            rss_mb=round(rss_mb, 1),
        )
