"""Tests for daemon lifecycle — PID file scenarios, startup/shutdown."""

from __future__ import annotations

import os
from pathlib import Path
from unittest.mock import AsyncMock, patch

import pytest

from silkroute.daemon.lifecycle import (
    DaemonContext,
    PidFileError,
    _is_process_running,
    shutdown,
    startup,
)


class TestIsProcessRunning:
    """PID liveness check."""

    def test_current_process_is_running(self) -> None:
        assert _is_process_running(os.getpid()) is True

    def test_nonexistent_pid(self) -> None:
        # PID 99999999 almost certainly doesn't exist
        assert _is_process_running(99999999) is False


class TestStartup:
    """Startup sequence — PID file handling."""

    @pytest.mark.asyncio
    async def test_creates_pid_file(self, tmp_path: Path) -> None:
        pid_path = tmp_path / "test.pid"
        sock_path = tmp_path / "test.sock"

        with patch("silkroute.daemon.redis_pool.get_redis", new_callable=AsyncMock) as mock_redis:
            mock_redis.return_value = AsyncMock()
            ctx = await startup(
                pid_path=pid_path,
                socket_path=sock_path,
                init_db=False,
            )

        assert pid_path.exists()
        assert int(pid_path.read_text().strip()) == os.getpid()
        assert ctx.redis is not None

    @pytest.mark.asyncio
    async def test_stale_pid_file_cleaned(self, tmp_path: Path) -> None:
        """Stale PID file (process not running) is removed and startup proceeds."""
        pid_path = tmp_path / "test.pid"
        sock_path = tmp_path / "test.sock"

        # Write a stale PID (process that doesn't exist)
        pid_path.write_text("99999999")

        with patch("silkroute.daemon.redis_pool.get_redis", new_callable=AsyncMock) as mock_redis:
            mock_redis.return_value = AsyncMock()
            ctx = await startup(
                pid_path=pid_path,
                socket_path=sock_path,
                init_db=False,
            )

        # PID file should now contain current process PID
        assert int(pid_path.read_text().strip()) == os.getpid()
        assert ctx is not None

    @pytest.mark.asyncio
    async def test_corrupt_pid_file_cleaned(self, tmp_path: Path) -> None:
        """Corrupt PID file (non-numeric) is removed and startup proceeds."""
        pid_path = tmp_path / "test.pid"
        sock_path = tmp_path / "test.sock"

        pid_path.write_text("not_a_number")

        with patch("silkroute.daemon.redis_pool.get_redis", new_callable=AsyncMock) as mock_redis:
            mock_redis.return_value = AsyncMock()
            ctx = await startup(
                pid_path=pid_path,
                socket_path=sock_path,
                init_db=False,
            )

        assert int(pid_path.read_text().strip()) == os.getpid()
        assert ctx is not None

    @pytest.mark.asyncio
    async def test_active_pid_raises_error(self, tmp_path: Path) -> None:
        """Active PID file (process running) raises PidFileError."""
        pid_path = tmp_path / "test.pid"
        sock_path = tmp_path / "test.sock"

        # Write the CURRENT process PID — it's definitely running
        pid_path.write_text(str(os.getpid()))

        with pytest.raises(PidFileError, match="already running"):
            await startup(
                pid_path=pid_path,
                socket_path=sock_path,
                init_db=False,
            )

    @pytest.mark.asyncio
    async def test_stale_socket_removed(self, tmp_path: Path) -> None:
        """Stale socket file is cleaned up on startup."""
        pid_path = tmp_path / "test.pid"
        sock_path = tmp_path / "test.sock"

        # Create a stale socket file
        sock_path.write_text("stale")

        with patch("silkroute.daemon.redis_pool.get_redis", new_callable=AsyncMock) as mock_redis:
            mock_redis.return_value = AsyncMock()
            await startup(
                pid_path=pid_path,
                socket_path=sock_path,
                init_db=False,
            )

        # Socket should have been removed during startup (not re-created — server does that)
        assert not sock_path.exists()

    @pytest.mark.asyncio
    async def test_redis_unreachable_raises(self, tmp_path: Path) -> None:
        """Startup fails if Redis is unreachable (daemon requires Redis)."""
        pid_path = tmp_path / "test.pid"
        sock_path = tmp_path / "test.sock"

        with patch("silkroute.daemon.redis_pool.get_redis", new_callable=AsyncMock) as mock_redis:
            mock_redis.return_value = None  # Redis unreachable
            with pytest.raises(RuntimeError, match="Redis is unreachable"):
                await startup(
                    pid_path=pid_path,
                    socket_path=sock_path,
                    init_db=False,
                )

    @pytest.mark.asyncio
    async def test_creates_parent_dirs(self, tmp_path: Path) -> None:
        """Parent directories are created if they don't exist."""
        pid_path = tmp_path / "deep" / "nested" / "test.pid"
        sock_path = tmp_path / "another" / "path" / "test.sock"

        with patch("silkroute.daemon.redis_pool.get_redis", new_callable=AsyncMock) as mock_redis:
            mock_redis.return_value = AsyncMock()
            await startup(
                pid_path=pid_path,
                socket_path=sock_path,
                init_db=False,
            )

        assert pid_path.exists()


class TestShutdown:
    """Shutdown sequence — cleanup and resource release."""

    @pytest.mark.asyncio
    async def test_removes_pid_file(self, tmp_path: Path) -> None:
        pid_file = tmp_path / "test.pid"
        sock_path = tmp_path / "test.sock"
        pid_file.write_text(str(os.getpid()))

        ctx = DaemonContext(
            pid_file=pid_file,
            socket_path=sock_path,
            redis=None,
            pool=None,
        )

        mock_queue = AsyncMock()
        mock_queue.drain = AsyncMock(return_value=[])

        await shutdown(ctx, mock_queue, [])
        assert not pid_file.exists()

    @pytest.mark.asyncio
    async def test_removes_socket_file(self, tmp_path: Path) -> None:
        pid_file = tmp_path / "test.pid"
        sock_path = tmp_path / "test.sock"
        pid_file.write_text(str(os.getpid()))
        sock_path.write_text("socket")

        ctx = DaemonContext(
            pid_file=pid_file,
            socket_path=sock_path,
            redis=None,
            pool=None,
        )

        mock_queue = AsyncMock()
        mock_queue.drain = AsyncMock(return_value=[])

        await shutdown(ctx, mock_queue, [])
        assert not sock_path.exists()

    @pytest.mark.asyncio
    async def test_drains_queue(self, tmp_path: Path) -> None:
        ctx = DaemonContext(
            pid_file=tmp_path / "test.pid",
            socket_path=tmp_path / "test.sock",
        )

        mock_queue = AsyncMock()
        mock_queue.drain = AsyncMock(return_value=["task1", "task2"])

        await shutdown(ctx, mock_queue, [])
        mock_queue.drain.assert_called_once()

    @pytest.mark.asyncio
    async def test_cancels_stuck_workers(self, tmp_path: Path) -> None:
        """Workers that don't finish within timeout are cancelled."""
        import asyncio

        ctx = DaemonContext(
            pid_file=tmp_path / "test.pid",
            socket_path=tmp_path / "test.sock",
        )

        async def stuck_worker() -> None:
            await asyncio.sleep(999)

        worker = asyncio.create_task(stuck_worker())
        mock_queue = AsyncMock()
        mock_queue.drain = AsyncMock(return_value=[])

        await shutdown(ctx, mock_queue, [worker], worker_timeout=0.1)
        assert worker.cancelled() or worker.done()
