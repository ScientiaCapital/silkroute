"""Tests for daemon server — lifecycle, socket protocol, signal handling."""

from __future__ import annotations

import asyncio
import json
import os
import tempfile
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from silkroute.daemon.server import DaemonServer


def _make_config(tmp_path: Path) -> object:
    """Create a DaemonConfig-like object for testing."""
    config = MagicMock()
    config.socket_path = str(tmp_path / "test.sock")
    config.pid_file = str(tmp_path / "test.pid")
    config.heartbeat_interval_seconds = 300  # Long interval — won't tick in tests
    config.max_concurrent_sessions = 2
    return config


class TestDaemonServer:
    """DaemonServer unit tests."""

    def test_init(self, tmp_path: Path) -> None:
        config = _make_config(tmp_path)
        server = DaemonServer(config)
        assert server._queue is not None
        assert not server._shutdown_event.is_set()
        assert server._workers == []

    @pytest.mark.asyncio
    async def test_handle_submit(self, tmp_path: Path) -> None:
        config = _make_config(tmp_path)
        server = DaemonServer(config)

        response = await server._handle_submit({
            "task": {"task": "review code", "project_id": "myproject"},
        })

        assert response["ok"] is True
        assert "id" in response
        assert server._queue.pending_count() == 1

    @pytest.mark.asyncio
    async def test_handle_submit_string_task(self, tmp_path: Path) -> None:
        config = _make_config(tmp_path)
        server = DaemonServer(config)

        response = await server._handle_submit({
            "task": "just a string task",
        })

        assert response["ok"] is True

    @pytest.mark.asyncio
    async def test_handle_submit_missing_task(self, tmp_path: Path) -> None:
        config = _make_config(tmp_path)
        server = DaemonServer(config)

        response = await server._handle_submit({"task": {}})

        assert response["ok"] is False
        assert "Missing" in response["error"]

    def test_handle_status(self, tmp_path: Path) -> None:
        config = _make_config(tmp_path)
        server = DaemonServer(config)

        status = server._handle_status()

        assert status["running"] is True
        assert status["pending"] == 0
        assert status["total_submitted"] == 0
        assert status["total_completed"] == 0
        assert status["max_workers"] == 2

    def test_handle_stop_sets_shutdown(self, tmp_path: Path) -> None:
        config = _make_config(tmp_path)
        server = DaemonServer(config)

        assert not server._shutdown_event.is_set()
        response = server._handle_stop()
        assert response["ok"] is True
        assert server._shutdown_event.is_set()

    @pytest.mark.asyncio
    async def test_handle_client_submit(self, tmp_path: Path) -> None:
        config = _make_config(tmp_path)
        server = DaemonServer(config)

        # Simulate reader/writer
        msg = json.dumps({"action": "submit", "task": {"task": "test"}}).encode()
        reader = AsyncMock()
        reader.read = AsyncMock(return_value=msg)
        writer = MagicMock()
        write_data = []
        writer.write = lambda data: write_data.append(data)
        writer.drain = AsyncMock()
        writer.close = MagicMock()
        writer.wait_closed = AsyncMock()

        await server._handle_client(reader, writer)

        assert len(write_data) == 1
        response = json.loads(write_data[0].decode())
        assert response["ok"] is True

    @pytest.mark.asyncio
    async def test_handle_client_status(self, tmp_path: Path) -> None:
        config = _make_config(tmp_path)
        server = DaemonServer(config)

        msg = json.dumps({"action": "status"}).encode()
        reader = AsyncMock()
        reader.read = AsyncMock(return_value=msg)
        writer = MagicMock()
        write_data = []
        writer.write = lambda data: write_data.append(data)
        writer.drain = AsyncMock()
        writer.close = MagicMock()
        writer.wait_closed = AsyncMock()

        await server._handle_client(reader, writer)

        response = json.loads(write_data[0].decode())
        assert response["running"] is True

    @pytest.mark.asyncio
    async def test_handle_client_invalid_json(self, tmp_path: Path) -> None:
        config = _make_config(tmp_path)
        server = DaemonServer(config)

        reader = AsyncMock()
        reader.read = AsyncMock(return_value=b"not json")
        writer = MagicMock()
        write_data = []
        writer.write = lambda data: write_data.append(data)
        writer.drain = AsyncMock()
        writer.close = MagicMock()
        writer.wait_closed = AsyncMock()

        await server._handle_client(reader, writer)

        response = json.loads(write_data[0].decode())
        assert response["ok"] is False
        assert "Invalid JSON" in response["error"]

    @pytest.mark.asyncio
    async def test_handle_client_unknown_action(self, tmp_path: Path) -> None:
        config = _make_config(tmp_path)
        server = DaemonServer(config)

        msg = json.dumps({"action": "unknown"}).encode()
        reader = AsyncMock()
        reader.read = AsyncMock(return_value=msg)
        writer = MagicMock()
        write_data = []
        writer.write = lambda data: write_data.append(data)
        writer.drain = AsyncMock()
        writer.close = MagicMock()
        writer.wait_closed = AsyncMock()

        await server._handle_client(reader, writer)

        response = json.loads(write_data[0].decode())
        assert response["ok"] is False
        assert "Unknown action" in response["error"]

    @pytest.mark.asyncio
    async def test_handle_client_empty_data(self, tmp_path: Path) -> None:
        config = _make_config(tmp_path)
        server = DaemonServer(config)

        reader = AsyncMock()
        reader.read = AsyncMock(return_value=b"")
        writer = MagicMock()
        writer.close = MagicMock()
        writer.wait_closed = AsyncMock()

        # Should return cleanly, no write
        await server._handle_client(reader, writer)

    def test_signal_handler_sets_shutdown(self, tmp_path: Path) -> None:
        import signal

        config = _make_config(tmp_path)
        server = DaemonServer(config)

        server._handle_signal(signal.SIGINT)
        assert server._shutdown_event.is_set()

    @pytest.mark.asyncio
    async def test_submit_with_all_options(self, tmp_path: Path) -> None:
        config = _make_config(tmp_path)
        server = DaemonServer(config)

        response = await server._handle_submit({
            "task": {
                "task": "complex analysis",
                "project_id": "proj-1",
                "model_override": "deepseek/deepseek-r1-0528",
                "tier_override": "premium",
                "max_iterations": 50,
                "budget_limit_usd": 25.0,
            },
        })

        assert response["ok"] is True
        # Verify request was created with correct params
        consumed = await server._queue.consume()
        assert consumed.task == "complex analysis"
        assert consumed.project_id == "proj-1"
        assert consumed.model_override == "deepseek/deepseek-r1-0528"
        assert consumed.tier_override == "premium"
        assert consumed.max_iterations == 50
        assert consumed.budget_limit_usd == 25.0
