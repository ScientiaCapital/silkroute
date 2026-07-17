"""Vendored mock epiphan MCP server — makes the AV demo fully self-contained.

Exposes exactly the 7 Pearl tools silkroute's epiphan allowlist expects, backed
by canned Pearl-2-Room320B data (the same narrative as pearl_mock_server.py, but
served directly over MCP so the demo needs NO external epiphan-mcp-server repo
and no HTTP layer). Run standalone over stdio:

    python demo/mock_epiphan_mcp.py

The AV demo points the bridge at this module via `--mock-mcp`.

Mirrors the pattern in src/silkroute/mcp_bridge/server.py: a low-level MCP
``Server`` with list_tools/call_tool, logging to stderr so stdout stays a clean
JSON-RPC channel.
"""

from __future__ import annotations

import asyncio
import contextlib
import json
import sys
from typing import Any

from mcp import types
from mcp.server import Server
from mcp.server.stdio import stdio_server

_DEVICE = {
    "name": "Pearl-2-Room320B",
    "model": "Pearl-2",
    "serial": "DEMO0320B",
    "firmware": "4.14.2",
    "mac": "00:11:22:33:44:55",
}

# tool name -> canned response object (the 7 allowlisted epiphan tools).
CANNED: dict[str, dict[str, Any]] = {
    "get_device_status": {
        "status": "ok",
        "result": {**_DEVICE, "state": "online", "uptime_seconds": 864_000},
    },
    "list_devices": {
        "status": "ok",
        "result": [{"host": "127.0.0.1", **_DEVICE, "state": "online"}],
    },
    "get_recording_status": {
        "status": "ok",
        "result": {
            "device": "Pearl-2-Room320B",
            "recorder_id": "recorder-1",
            "recorder_name": "Room 320-B Recorder",
            "state": "recording",
            "duration_seconds": 1800,
            "file_size_bytes": 536_870_912,
            "filename": "room_320b_2026-07-12_09-00-00.mp4",
        },
    },
    "list_recorders": {
        "status": "ok",
        "result": [
            {
                "id": "recorder-1",
                "name": "Room 320-B Recorder",
                "type": "mp4",
                "channel_id": "channel-1",
            },
        ],
    },
    "get_all_recorder_status": {
        "status": "ok",
        "result": [
            {
                "id": "recorder-1",
                "device": "Pearl-2-Room320B",
                "state": "recording",
                "duration_seconds": 1800,
            },
        ],
    },
    "get_system_info": {
        "status": "ok",
        "result": {**_DEVICE, "cpu_percent": 22.5, "storage_free_bytes": 400_000_000_000},
    },
    "get_fleet_status": {
        "status": "ok",
        "result": {
            "devices_total": 1,
            "devices_online": 1,
            "recorders_active": 1,
            "devices": [{"name": "Pearl-2-Room320B", "state": "online", "recording": True}],
        },
    },
}

_DESCRIPTIONS: dict[str, str] = {
    "get_device_status": "Get a Pearl device's online status and identity.",
    "list_devices": "List all Pearl devices in the fleet.",
    "get_recording_status": "Get the current recording state for the room's recorder.",
    "list_recorders": "List the recorders configured on the device.",
    "get_all_recorder_status": "Get the recording state of every recorder.",
    "get_system_info": "Get device system info (firmware, CPU, storage).",
    "get_fleet_status": "Get a fleet-wide summary (devices online, recorders active).",
}

_EMPTY_SCHEMA: dict[str, Any] = {"type": "object", "properties": {}, "required": []}


def list_tool_names() -> list[str]:
    """Names of the tools this stub serves (the 7 allowlisted epiphan tools)."""
    return list(CANNED)


def call_tool_text(name: str, arguments: dict[str, Any] | None = None) -> str:
    """Return the canned JSON response for a tool call, as text."""
    body = CANNED.get(name)
    if body is None:
        return json.dumps({"status": "error", "message": f"Unknown tool '{name}'"})
    return json.dumps(body)


def build_server(name: str = "mock-epiphan") -> Server:
    """Build the MCP server exposing the canned Pearl tools."""
    server: Server = Server(name)

    @server.list_tools()
    async def _list_tools() -> list[types.Tool]:
        return [
            types.Tool(name=n, description=_DESCRIPTIONS[n], inputSchema=_EMPTY_SCHEMA)
            for n in list_tool_names()
        ]

    @server.call_tool()
    async def _call_tool(name: str, arguments: dict[str, Any]) -> list[types.TextContent]:
        return [types.TextContent(type="text", text=call_tool_text(name, arguments))]

    return server


async def serve_stdio() -> None:
    """Run the mock epiphan MCP server over stdio."""
    server = build_server()
    print("[mock-epiphan] serving 7 Pearl tools (Pearl-2-Room320B)", file=sys.stderr)
    async with stdio_server() as (read_stream, write_stream):
        await server.run(read_stream, write_stream, server.create_initialization_options())


def main() -> None:
    with contextlib.suppress(KeyboardInterrupt):
        asyncio.run(serve_stdio())


if __name__ == "__main__":
    main()
