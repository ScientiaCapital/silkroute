"""Tests for exposing SilkRoute's ToolRegistry as an MCP server.

This is the inverse of the MCP client bridge: ToolSpec -> MCP Tool. The default
export policy is read-only (no shell_exec / write_file / http_request) so the
server isn't a remote code-exec / SSRF surface unless explicitly opted in.
"""

from __future__ import annotations

import sys

import pytest

from silkroute.agent.tools import ToolRegistry, ToolSpec, create_default_registry
from silkroute.mcp_bridge.client import connect_mcp_server
from silkroute.mcp_bridge.server import (
    DEFAULT_EXPORT_ALLOWLIST,
    build_mcp_server,
    dispatch_tool,
    select_exported_specs,
    spec_to_mcp_tool,
)


def _registry() -> ToolRegistry:
    return create_default_registry()


class TestExportAllowlist:
    def test_default_excludes_dangerous_tools(self) -> None:
        names = {s.name for s in select_exported_specs(_registry(), None)}
        assert "shell_exec" not in names
        assert "write_file" not in names
        assert "http_request" not in names

    def test_default_includes_readonly_tools(self) -> None:
        names = {s.name for s in select_exported_specs(_registry(), None)}
        assert {"read_file", "list_directory", "search_grep", "git_ops", "env_info"} <= names

    def test_custom_allowlist_opts_in(self) -> None:
        specs = select_exported_specs(_registry(), {"shell_exec"})
        assert [s.name for s in specs] == ["shell_exec"]

    def test_empty_allowlist_exports_nothing(self) -> None:
        assert select_exported_specs(_registry(), frozenset()) == []

    def test_unknown_names_ignored(self) -> None:
        specs = select_exported_specs(_registry(), {"read_file", "does_not_exist"})
        assert [s.name for s in specs] == ["read_file"]


class TestSpecMapping:
    def test_spec_maps_to_mcp_tool(self) -> None:
        spec = ToolSpec(
            name="demo",
            description="A demo tool",
            parameters={"type": "object", "properties": {"x": {"type": "string"}}},
            handler=lambda **_: "ok",  # type: ignore[arg-type,return-value]
        )
        tool = spec_to_mcp_tool(spec)
        assert tool.name == "demo"
        assert tool.description == "A demo tool"
        assert tool.inputSchema == spec.parameters


class TestDispatch:
    @pytest.mark.asyncio
    async def test_allowed_tool_executes(self) -> None:
        result = await dispatch_tool(_registry(), "env_info", {"query": "cwd"}, None)
        assert "CWD" in result

    @pytest.mark.asyncio
    async def test_disallowed_tool_blocked(self) -> None:
        # shell_exec is not in the default export allowlist — must be refused
        # WITHOUT executing.
        result = await dispatch_tool(_registry(), "shell_exec", {"command": "echo pwned"}, None)
        assert "not exported" in result
        assert "pwned" not in result


class TestBuildServer:
    def test_build_returns_named_server(self) -> None:
        server = build_mcp_server(_registry(), name="silkroute")
        assert server.name == "silkroute"

    def test_default_allowlist_is_readonly(self) -> None:
        assert "shell_exec" not in DEFAULT_EXPORT_ALLOWLIST
        assert "read_file" in DEFAULT_EXPORT_ALLOWLIST


class TestRoundTrip:
    """End-to-end: SilkRoute's own bridge drives `silkroute mcp serve`.

    Proves both directions interoperate (ToolSpec -> MCP -> ToolSpec) and that
    the default read-only export policy holds across the real stdio transport.
    """

    @pytest.mark.asyncio
    async def test_bridge_connects_to_own_server(self) -> None:
        registry = ToolRegistry()
        stack = await connect_mcp_server(
            registry,
            command=sys.executable,
            args=["-m", "silkroute.cli", "mcp", "serve"],
        )
        assert stack is not None, "bridge failed to connect to our own MCP server"
        try:
            names = set(registry.tool_names)
            # Read-only tools exposed; dangerous tools must NOT leak.
            assert {"read_file", "env_info", "list_directory"} <= names
            assert "shell_exec" not in names
            assert "write_file" not in names
            # A real call round-trips through the transport.
            result = await registry.execute("env_info", {"query": "cwd"})
            assert "CWD" in result
        finally:
            await stack.aclose()
