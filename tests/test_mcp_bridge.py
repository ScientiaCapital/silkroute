"""Tests for silkroute.mcp_bridge.client against a tiny fixture MCP server.

Each test opens and closes its own connection within a single test coroutine
(rather than sharing an async yield-fixture) — anyio's cancel scopes are
task-bound, and a fixture's teardown can run in a different task than its
setup under pytest-asyncio, raising "cancel scope in a different task."
"""

import sys
from pathlib import Path

from silkroute.agent.tools import ToolRegistry
from silkroute.mcp_bridge.client import connect_mcp_server

FIXTURE_SERVER = str(Path(__file__).parent / "fixtures" / "fake_mcp_server.py")


class TestConnectMcpServer:
    async def test_registers_all_tools_when_no_allowlist(self) -> None:
        registry = ToolRegistry()
        stack = await connect_mcp_server(registry, command=sys.executable, args=[FIXTURE_SERVER])
        assert stack is not None
        try:
            names = set(registry.tool_names)
            assert {"echo", "always_fails", "not_allowlisted"} <= names
        finally:
            await stack.aclose()

    async def test_allowlist_filters_tools(self) -> None:
        registry = ToolRegistry()
        stack = await connect_mcp_server(
            registry,
            command=sys.executable,
            args=[FIXTURE_SERVER],
            tool_allowlist=["echo"],
        )
        assert stack is not None
        try:
            assert registry.tool_names == ["echo"]
        finally:
            await stack.aclose()

    async def test_execute_round_trips_success(self) -> None:
        registry = ToolRegistry()
        stack = await connect_mcp_server(registry, command=sys.executable, args=[FIXTURE_SERVER])
        assert stack is not None
        try:
            result = await registry.execute("echo", {"message": "hello"})
            assert result == "echo: hello"
        finally:
            await stack.aclose()

    async def test_execute_maps_tool_error_to_error_string(self) -> None:
        registry = ToolRegistry()
        stack = await connect_mcp_server(registry, command=sys.executable, args=[FIXTURE_SERVER])
        assert stack is not None
        try:
            result = await registry.execute("always_fails", {})
            assert result.startswith("Error")
            assert "intentional failure" in result
        finally:
            await stack.aclose()

    async def test_connect_failure_is_non_fatal(self) -> None:
        registry = ToolRegistry()
        stack = await connect_mcp_server(registry, command="/no/such/executable", args=[])
        assert stack is None
        assert registry.tool_names == []
