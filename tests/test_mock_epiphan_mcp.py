"""Tests for the vendored mock epiphan MCP server (demo/mock_epiphan_mcp.py).

This stub lets the AV demo run fully self-contained — no external
epiphan-mcp-server repo — by exposing the 7 allowlisted Pearl tools backed by
canned Pearl-2-Room320B data.
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

import pytest

# demo/ is not a package; add it to the path like the demo scripts do.
_DEMO_DIR = str(Path(__file__).parent.parent / "demo")
if _DEMO_DIR not in sys.path:
    sys.path.insert(0, _DEMO_DIR)

import mock_epiphan_mcp as stub  # noqa: E402

# The 7 tools silkroute's epiphan allowlist expects (settings.MCPConfig default).
EXPECTED_TOOLS = {
    "get_device_status",
    "list_devices",
    "get_recording_status",
    "list_recorders",
    "get_all_recorder_status",
    "get_system_info",
    "get_fleet_status",
}


class TestToolCatalog:
    def test_exposes_the_seven_allowlisted_tools(self) -> None:
        assert set(stub.list_tool_names()) == EXPECTED_TOOLS


class TestCannedResponses:
    def test_recording_status_reports_room_320b_recording(self) -> None:
        text = stub.call_tool_text("get_recording_status", {})
        payload = json.loads(text)  # must be valid JSON
        assert "recording" in text.lower()
        assert "320" in text  # room 320-B narrative
        assert payload  # non-empty

    def test_list_devices_includes_pearl_room_320b(self) -> None:
        text = stub.call_tool_text("list_devices", {})
        assert "Pearl-2-Room320B" in text

    def test_unknown_tool_returns_error_json(self) -> None:
        text = stub.call_tool_text("does_not_exist", {})
        payload = json.loads(text)
        assert payload.get("status") == "error" or "error" in text.lower()


class TestServer:
    def test_build_server_named(self) -> None:
        server = stub.build_server()
        assert server.name  # a non-empty MCP server name


class TestBridgeRoundTrip:
    """The silkroute bridge connects to the vendored stub over real stdio."""

    @pytest.mark.asyncio
    async def test_bridge_discovers_pearl_tools(self) -> None:
        from silkroute.agent.tools import ToolRegistry
        from silkroute.mcp_bridge.client import connect_mcp_server

        registry = ToolRegistry()
        stack = await connect_mcp_server(
            registry,
            command=sys.executable,
            args=[str(Path(_DEMO_DIR) / "mock_epiphan_mcp.py")],
        )
        assert stack is not None, "bridge failed to connect to the mock epiphan server"
        try:
            assert EXPECTED_TOOLS <= set(registry.tool_names)
            result = await registry.execute("get_recording_status", {})
            assert "recording" in result.lower()
            assert "320" in result
        finally:
            await stack.aclose()
