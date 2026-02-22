"""Daemon lifecycle management — startup, shutdown, PID file locking.

Orchestrates the initialization and teardown of all daemon subsystems:
Redis pool, DB pool, PID file, socket cleanup, and graceful worker drain.
"""

from __future__ import annotations

import asyncio
import os
from dataclasses import dataclass, field
from datetime import UTC, datetime
from pathlib import Path

import redis.asyncio as aioredis
import structlog

from silkroute.daemon.queue import TaskQueue

log = structlog.get_logger()


@dataclass
class DaemonContext:
    """Runtime state for the daemon process."""

    pid_file: Path
    socket_path: Path
    redis: aioredis.Redis | None = None
    pool: object | None = None  # asyncpg.Pool or None
    started_at: datetime = field(default_factory=lambda: datetime.now(UTC))


class PidFileError(Exception):
    """Raised when another daemon instance is already running."""


def _is_process_running(pid: int) -> bool:
    """Check if a process with the given PID is alive."""
    try:
        os.kill(pid, 0)
        return True
    except (ProcessLookupError, PermissionError):
        return False


async def startup(
    *,
    pid_path: str | Path,
    socket_path: str | Path,
    init_db: bool = True,
) -> DaemonContext:
    """Initialize the daemon: check PID file, write PID, optionally init DB pool.

    Raises PidFileError if another daemon is already running.
    """
    pid_file = Path(pid_path).expanduser()
    sock_path = Path(socket_path).expanduser()

    # Ensure parent directories exist
    pid_file.parent.mkdir(parents=True, exist_ok=True)
    sock_path.parent.mkdir(parents=True, exist_ok=True)

    # Check for existing daemon
    if pid_file.exists():
        try:
            existing_pid = int(pid_file.read_text().strip())
            if _is_process_running(existing_pid):
                raise PidFileError(
                    f"Daemon already running (PID {existing_pid}). "
                    f"Stop it with 'silkroute daemon stop' or remove {pid_file}"
                )
            else:
                log.warning("stale_pid_file", pid=existing_pid, path=str(pid_file))
                pid_file.unlink()
        except ValueError:
            log.warning("corrupt_pid_file", path=str(pid_file))
            pid_file.unlink()

    # Remove stale socket
    if sock_path.exists():
        sock_path.unlink()
        log.info("stale_socket_removed", path=str(sock_path))

    # Write PID file
    pid_file.write_text(str(os.getpid()))
    log.info("pid_file_written", pid=os.getpid(), path=str(pid_file))

    # Initialize Redis (required — daemon cannot function without it)
    from silkroute.daemon.redis_pool import get_redis

    redis_client = await get_redis()
    if redis_client is None:
        raise RuntimeError(
            "Redis is unreachable. The daemon requires Redis for task queue persistence. "
            "Start Redis with 'docker compose up -d redis' or check SILKROUTE_DB_REDIS_URL."
        )
    log.info("redis_connected")

    # Initialize DB pool (optional, graceful failure)
    pool = None
    if init_db:
        try:
            from silkroute.db.pool import get_pool

            pool = await get_pool()
            if pool is not None:
                log.info("db_pool_connected")
            else:
                log.warning("db_pool_unavailable")
        except Exception as exc:
            log.warning("db_pool_init_failed", error=str(exc))

    return DaemonContext(
        pid_file=pid_file,
        socket_path=sock_path,
        redis=redis_client,
        pool=pool,
    )


async def shutdown(
    context: DaemonContext,
    queue: TaskQueue,
    workers: list[asyncio.Task],
    *,
    worker_timeout: float = 30.0,
) -> None:
    """Graceful shutdown: drain queue, await workers, close pool, clean up files."""
    log.info("shutdown_initiated")

    # Drain remaining queue items
    drained = await queue.drain()
    if drained:
        log.warning("shutdown_drained_tasks", count=len(drained))

    # Wait for in-flight workers
    if workers:
        active = [w for w in workers if not w.done()]
        if active:
            log.info("shutdown_awaiting_workers", count=len(active))
            done, pending = await asyncio.wait(active, timeout=worker_timeout)
            if pending:
                log.warning("shutdown_cancelling_workers", count=len(pending))
                for task in pending:
                    task.cancel()
                await asyncio.gather(*pending, return_exceptions=True)

    # Close Redis
    if context.redis is not None:
        try:
            from silkroute.daemon.redis_pool import close_redis

            await close_redis()
            log.info("redis_closed")
        except Exception as exc:
            log.warning("redis_close_failed", error=str(exc))

    # Close DB pool
    if context.pool is not None:
        try:
            from silkroute.db.pool import close_pool

            await close_pool()
            log.info("db_pool_closed")
        except Exception as exc:
            log.warning("db_pool_close_failed", error=str(exc))

    # Remove PID file
    if context.pid_file.exists():
        context.pid_file.unlink()
        log.info("pid_file_removed", path=str(context.pid_file))

    # Remove socket file
    if context.socket_path.exists():
        context.socket_path.unlink()
        log.info("socket_removed", path=str(context.socket_path))

    log.info("shutdown_complete")
