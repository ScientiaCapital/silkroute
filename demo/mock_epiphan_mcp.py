"""Vendored mock epiphan MCP server — makes the AV demo fully self-contained.

Exposes the Pearl tools silkroute's epiphan allowlist expects, backed by a
mutable Pearl-2-Room320B room model. Two tool classes:

- 7 READ tools (get_device_status, get_recording_status, get_system_info, …) —
  serialize the current room state.
- 6 ACTION tools (start_recorder, restart_input, reboot_device, …) — MUTATE the
  room to clear a fault, so a re-read verifies the fix. These are the self-healing
  remediation actions; they exist ONLY on this mock and are reached only via an
  allowlist the caller passes explicitly (the production epiphan allowlist stays
  read-only).

The room defaults to the healthy recording narrative (byte-compatible with the
prior static mock). A fault can be injected at spawn via the env var
``SILKROUTE_MOCK_ROOM_FAULT=<fault_type>`` so the heal executor can demonstrate
detect → fix → verify.

Run standalone over stdio:  python demo/mock_epiphan_mcp.py
The AV demo points the bridge at this module via `--mock-mcp`.
"""

from __future__ import annotations

import asyncio
import contextlib
import json
import os
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


def _default_room() -> dict[str, Any]:
    """Healthy baseline — matches the prior static mock's values."""
    return {
        "device_state": "online",
        "recorder_state": "recording",
        "input_has_signal": True,
        "storage_mounted": True,
        "storage_percent_used": 22,
        "cpu_percent": 22.5,
        "uptime_seconds": 864_000,
        "duration_seconds": 1800,
        "file_size_bytes": 536_870_912,
        "filename": "room_320b_2026-07-12_09-00-00.mp4",
    }


# Each fault breaks exactly one signal (storage_unmounted / device_offline also
# stop the recorder, as a real room would). Keys must match _default_room signals.
_FAULTS: dict[str, dict[str, Any]] = {
    "recorder_stopped": {"recorder_state": "stopped"},
    "signal_loss": {"input_has_signal": False},
    "storage_full": {"storage_percent_used": 95},
    "storage_unmounted": {"storage_mounted": False, "recorder_state": "stopped"},
    "device_offline": {"device_state": "offline", "recorder_state": "stopped"},
    "cpu_overload": {"cpu_percent": 97.0},
}

# Mutable room state for this process. Initialized from the env-var fault (if any).
_ROOM: dict[str, Any] = _default_room()


def reset_room(fault: str | None = None) -> None:
    """Reset the room to healthy, then apply an optional fault (for tests/spawn)."""
    _ROOM.clear()
    _ROOM.update(_default_room())
    if fault and fault in _FAULTS:
        _ROOM.update(_FAULTS[fault])


# Apply the env-var fault at import (set by the heal executor when it spawns us).
reset_room(os.environ.get("SILKROUTE_MOCK_ROOM_FAULT") or None)


_READ_TOOLS = [
    "get_device_status",
    "list_devices",
    "get_recording_status",
    "list_recorders",
    "get_all_recorder_status",
    "get_system_info",
    "get_fleet_status",
]

# Remediation actions → the signal mutation that clears the corresponding fault.
_ACTION_EFFECTS: dict[str, dict[str, Any]] = {
    "start_recorder": {"recorder_state": "recording", "duration_seconds": 0},
    "restart_input": {"input_has_signal": True},
    "rotate_recordings": {"storage_percent_used": 22},
    "remount_storage": {"storage_mounted": True},
    # A reboot brings the device back online and recording (clears device_offline).
    "reboot_device": {"device_state": "online", "recorder_state": "recording"},
    "throttle_channels": {"cpu_percent": 22.5},
}
_ACTION_TOOLS = list(_ACTION_EFFECTS)


def _read_response(name: str) -> dict[str, Any] | None:
    """Serialize the current room state for a read tool."""
    recording = _ROOM["recorder_state"] == "recording"
    online = _ROOM["device_state"] == "online"
    if name == "get_device_status":
        return {
            "status": "ok",
            "result": {
                **_DEVICE,
                "state": _ROOM["device_state"],
                "uptime_seconds": _ROOM["uptime_seconds"],
                "input_has_signal": _ROOM["input_has_signal"],
            },
        }
    if name == "list_devices":
        return {
            "status": "ok",
            "result": [{"host": "127.0.0.1", **_DEVICE, "state": _ROOM["device_state"]}],
        }
    if name == "get_recording_status":
        return {
            "status": "ok",
            "result": {
                "device": "Pearl-2-Room320B",
                "recorder_id": "recorder-1",
                "recorder_name": "Room 320-B Recorder",
                "state": _ROOM["recorder_state"],
                "duration_seconds": _ROOM["duration_seconds"],
                "file_size_bytes": _ROOM["file_size_bytes"],
                "filename": _ROOM["filename"],
            },
        }
    if name == "list_recorders":
        return {
            "status": "ok",
            "result": [
                {
                    "id": "recorder-1",
                    "name": "Room 320-B Recorder",
                    "type": "mp4",
                    "channel_id": "channel-1",
                },
            ],
        }
    if name == "get_all_recorder_status":
        return {
            "status": "ok",
            "result": [
                {
                    "id": "recorder-1",
                    "device": "Pearl-2-Room320B",
                    "state": _ROOM["recorder_state"],
                    "duration_seconds": _ROOM["duration_seconds"],
                },
            ],
        }
    if name == "get_system_info":
        # storage_free_bytes derived from percent used (0.5TB nominal capacity).
        free = int((100 - _ROOM["storage_percent_used"]) / 100 * 512_000_000_000)
        return {
            "status": "ok",
            "result": {
                **_DEVICE,
                "cpu_percent": _ROOM["cpu_percent"],
                "storage_free_bytes": free,
                "storage_percent_used": _ROOM["storage_percent_used"],
                "storage_mounted": _ROOM["storage_mounted"],
            },
        }
    if name == "get_fleet_status":
        return {
            "status": "ok",
            "result": {
                "devices_total": 1,
                "devices_online": 1 if online else 0,
                "recorders_active": 1 if recording else 0,
                "devices": [
                    {
                        "name": "Pearl-2-Room320B",
                        "state": _ROOM["device_state"],
                        "recording": recording,
                    }
                ],
            },
        }
    return None


def _apply_action(name: str) -> dict[str, Any]:
    """Mutate the room to clear the fault the action addresses."""
    effect = _ACTION_EFFECTS.get(name)
    if effect is None:
        return {"status": "error", "message": f"Unknown action '{name}'"}
    _ROOM.update(effect)
    return {"status": "ok", "result": {"action": name, "applied": True}}


_DESCRIPTIONS: dict[str, str] = {
    "get_device_status": "Get a Pearl device's online status, identity, and input signal.",
    "list_devices": "List all Pearl devices in the fleet.",
    "get_recording_status": "Get the current recording state for the room's recorder.",
    "list_recorders": "List the recorders configured on the device.",
    "get_all_recorder_status": "Get the recording state of every recorder.",
    "get_system_info": "Get device system info (firmware, CPU, storage mount + usage).",
    "get_fleet_status": "Get a fleet-wide summary (devices online, recorders active).",
    "start_recorder": "Start the room's recorder (remediates a stopped recorder).",
    "restart_input": "Restart the video input (remediates a lost input signal).",
    "rotate_recordings": "Rotate/prune old recordings to free storage (remediates full storage).",
    "remount_storage": "Remount the storage volume (remediates unmounted storage).",
    "reboot_device": "Reboot the device (remediates an offline device).",
    "throttle_channels": "Throttle channel bitrate to shed CPU load (remediates CPU overload).",
}

_EMPTY_SCHEMA: dict[str, Any] = {"type": "object", "properties": {}, "required": []}
# Action tools accept an optional free-text reason (for audit); no required args.
_ACTION_SCHEMA: dict[str, Any] = {
    "type": "object",
    "properties": {"reason": {"type": "string", "description": "Why the action is applied"}},
    "required": [],
}


def list_tool_names() -> list[str]:
    """Names of the tools this stub serves (7 read + 6 action)."""
    return _READ_TOOLS + _ACTION_TOOLS


def call_tool_text(name: str, arguments: dict[str, Any] | None = None) -> str:
    """Return a tool's response as JSON text (read = serialize, action = mutate)."""
    if name in _ACTION_EFFECTS:
        return json.dumps(_apply_action(name))
    body = _read_response(name)
    if body is None:
        return json.dumps({"status": "error", "message": f"Unknown tool '{name}'"})
    return json.dumps(body)


def build_server(name: str = "mock-epiphan") -> Server:
    """Build the MCP server exposing the read + action Pearl tools."""
    server: Server = Server(name)

    @server.list_tools()
    async def _list_tools() -> list[types.Tool]:
        return [
            types.Tool(
                name=n,
                description=_DESCRIPTIONS[n],
                inputSchema=_ACTION_SCHEMA if n in _ACTION_EFFECTS else _EMPTY_SCHEMA,
            )
            for n in list_tool_names()
        ]

    @server.call_tool()
    async def _call_tool(name: str, arguments: dict[str, Any]) -> list[types.TextContent]:
        return [types.TextContent(type="text", text=call_tool_text(name, arguments))]

    return server


async def serve_stdio() -> None:
    """Run the mock epiphan MCP server over stdio."""
    server = build_server()
    fault = os.environ.get("SILKROUTE_MOCK_ROOM_FAULT") or "none"
    print(
        f"[mock-epiphan] serving {len(list_tool_names())} Pearl tools "
        f"(Pearl-2-Room320B, fault={fault})",
        file=sys.stderr,
    )
    async with stdio_server() as (read_stream, write_stream):
        await server.run(read_stream, write_stream, server.create_initialization_options())


def main() -> None:
    with contextlib.suppress(KeyboardInterrupt):
        asyncio.run(serve_stdio())


if __name__ == "__main__":
    main()
