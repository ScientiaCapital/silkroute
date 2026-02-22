"""Daemon server — main entry point for the SilkRoute daemon process.

Orchestrates the Unix socket listener, worker pool, heartbeat ticker,
scheduler, and signal handling. The run() method blocks until shutdown.
"""

from __future__ import annotations

import asyncio
import json
import signal

import structlog

from silkroute.config.settings import DaemonConfig
from silkroute.daemon.heartbeat import HeartbeatTicker
from silkroute.daemon.lifecycle import DaemonContext, shutdown, startup
from silkroute.daemon.queue import TaskQueue, TaskRequest
from silkroute.daemon.scheduler import DaemonScheduler
from silkroute.daemon.worker import worker_loop

log = structlog.get_logger()


class DaemonServer:
    """Main daemon process: event loop, socket API, worker pool, heartbeat, scheduler.

    Usage::

        config = DaemonConfig()
        server = DaemonServer(config)
        asyncio.run(server.run())
    """

    def __init__(self, config: DaemonConfig) -> None:
        self._config = config
        self._queue: TaskQueue | None = None
        self._shutdown_event = asyncio.Event()
        self._workers: list[asyncio.Task] = []
        self._context: DaemonContext | None = None
        self._socket_server: asyncio.AbstractServer | None = None
        self._scheduler: DaemonScheduler | None = None
        self._active_worker_count = 0

    async def run(self) -> None:
        """Main daemon entry point. Blocks until shutdown signal."""
        log.info(
            "daemon_starting",
            max_workers=self._config.max_concurrent_sessions,
            heartbeat_interval=self._config.heartbeat_interval_seconds,
            socket_path=self._config.socket_path,
        )

        # 1. Register signal handlers
        loop = asyncio.get_running_loop()
        for sig in (signal.SIGINT, signal.SIGTERM):
            loop.add_signal_handler(sig, self._handle_signal, sig)

        # 2. Run startup sequence (includes Redis init)
        self._context = await startup(
            pid_path=self._config.pid_file,
            socket_path=self._config.socket_path,
        )

        # 3. Create Redis-backed queue
        self._queue = TaskQueue(redis=self._context.redis)
        await self._queue.init_counters()

        try:
            # 4. Start scheduler
            self._scheduler = DaemonScheduler(self._config, self._queue)
            self._scheduler.start()

            # 5. Start heartbeat ticker
            heartbeat = HeartbeatTicker(
                interval=self._config.heartbeat_interval_seconds,
                queue=self._queue,
                active_workers_fn=lambda: self._active_worker_count,
            )
            heartbeat.start()

            # 6. Start worker tasks
            for i in range(self._config.max_concurrent_sessions):
                task = asyncio.create_task(
                    self._worker_wrapper(i + 1),
                    name=f"worker-{i + 1}",
                )
                self._workers.append(task)

            # 7. Start Unix socket server
            await self._start_socket_server()

            log.info("daemon_ready")

            # 8. Wait for shutdown signal
            await self._shutdown_event.wait()

        finally:
            # 9. Shutdown sequence
            log.info("daemon_shutting_down")

            # Stop scheduler first (prevents new task submissions)
            if self._scheduler is not None:
                await self._scheduler.stop()

            await heartbeat.stop()

            if self._socket_server is not None:
                self._socket_server.close()
                await self._socket_server.wait_closed()

            # Signal workers to stop
            self._shutdown_event.set()
            await shutdown(
                self._context,
                self._queue,
                self._workers,
            )

            log.info("daemon_stopped")

    async def _worker_wrapper(self, worker_id: int) -> None:
        """Wrap worker_loop to track active count."""
        await worker_loop(
            worker_id=worker_id,
            queue=self._queue,
            shutdown_event=self._shutdown_event,
        )

    async def _start_socket_server(self) -> None:
        """Listen on Unix socket for client connections."""
        from pathlib import Path

        socket_path = Path(self._config.socket_path).expanduser()
        self._socket_server = await asyncio.start_unix_server(
            self._handle_client,
            path=str(socket_path),
        )
        log.info("socket_server_listening", path=str(socket_path))

    async def _handle_client(
        self,
        reader: asyncio.StreamReader,
        writer: asyncio.StreamWriter,
    ) -> None:
        """Handle a single client connection: read JSON, dispatch action, respond."""
        try:
            data = await reader.read(65536)
            if not data:
                return

            msg = json.loads(data.decode())
            action = msg.get("action", "")

            if action == "submit":
                response = await self._handle_submit(msg)
            elif action == "status":
                response = await self._handle_status()
            elif action == "stop":
                response = self._handle_stop()
            else:
                response = {"ok": False, "error": f"Unknown action: {action}"}

            writer.write(json.dumps(response).encode())
            await writer.drain()

        except json.JSONDecodeError:
            writer.write(json.dumps({"ok": False, "error": "Invalid JSON"}).encode())
            await writer.drain()
        except Exception as exc:
            log.error("client_handler_error", error=str(exc))
        finally:
            writer.close()
            await writer.wait_closed()

    async def _handle_submit(self, msg: dict) -> dict:
        """Process a task submission."""
        task_data = msg.get("task", {})
        if isinstance(task_data, str):
            task_data = {"task": task_data}

        task_str = task_data.get("task", "")
        if not task_str:
            return {"ok": False, "error": "Missing 'task' field"}

        request = TaskRequest(
            task=task_str,
            project_id=task_data.get("project_id", "default"),
            model_override=task_data.get("model_override"),
            tier_override=task_data.get("tier_override"),
            max_iterations=task_data.get("max_iterations", 25),
            budget_limit_usd=task_data.get("budget_limit_usd", 10.0),
        )

        await self._queue.submit(request)
        log.info("task_submitted", request_id=request.id, task=task_str[:100])

        return {"ok": True, "id": request.id}

    async def _handle_status(self) -> dict:
        """Return daemon status summary."""
        active_count = sum(1 for w in self._workers if not w.done())
        uptime = 0.0
        if self._context is not None:
            from datetime import UTC, datetime

            uptime = (datetime.now(UTC) - self._context.started_at).total_seconds()

        status = {
            "running": True,
            "pending": await self._queue.pending_count(),
            "active_workers": active_count,
            "total_submitted": self._queue.total_submitted,
            "total_completed": self._queue.total_completed,
            "max_workers": self._config.max_concurrent_sessions,
            "uptime_seconds": int(uptime),
        }

        if self._scheduler is not None:
            status["scheduler_jobs"] = self._scheduler.get_jobs()

        return status

    def _handle_stop(self) -> dict:
        """Initiate graceful shutdown."""
        log.info("stop_requested_via_socket")
        self._shutdown_event.set()
        return {"ok": True}

    def _handle_signal(self, sig: signal.Signals) -> None:
        """Signal handler: set the shutdown event."""
        log.info("signal_received", signal=sig.name)
        self._shutdown_event.set()
