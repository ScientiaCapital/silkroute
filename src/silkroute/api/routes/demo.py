"""AV/edge demo endpoints — live room state + streaming agent trace.

Public (un-gated) endpoints that back the dashboard's `/demo` page. They spend
NO money — everything is served from the vendored mock epiphan MCP server
(`demo/mock_epiphan_mcp.py`), so unlike `/runtime/*` there is no `require_auth`
/ `require_not_demo` gate.

    GET /demo/room     → current mock room/device state (JSON snapshot)
    GET /demo/stream   → Server-Sent Events: a Think → Act → Observe agent trace

The stream is a *deterministic replay* driven by the real mock tool outputs
(`call_tool_text`), not a live LLM run — matching the self-contained-mock
philosophy of the demo (the dashboard falls back to the same narrative when the
API is unreachable). A live mode that swaps in `run_agent` is a future toggle;
the replay is what makes the page work with zero external deps (no Ollama, no
API key, no DB) on a fresh clone or a static Vercel deployment.
"""

from __future__ import annotations

import asyncio
import json
from collections.abc import AsyncIterator
from typing import Any

from fastapi import APIRouter, Query
from fastapi.responses import StreamingResponse
from pydantic import BaseModel

router = APIRouter(prefix="/demo", tags=["demo"])

DEFAULT_TASK = "did recording start in room 320-B"
DEFAULT_MODEL = "ollama/qwen2.5:14b"

# Fallback room snapshot — used only if demo/mock_epiphan_mcp.py is not importable
# (e.g. a deployment that excludes the repo-root demo/ dir). Mirrors the mock's
# Pearl-2-Room320B narrative so the endpoint always returns something coherent.
_FALLBACK_TOOLS: dict[str, dict[str, Any]] = {
    "get_recording_status": {
        "status": "ok",
        "result": {
            "device": "Pearl-2-Room320B",
            "recorder_name": "Room 320-B Recorder",
            "state": "recording",
            "duration_seconds": 1800,
            "file_size_bytes": 536_870_912,
            "filename": "room_320b_2026-07-12_09-00-00.mp4",
        },
    },
    "get_system_info": {
        "status": "ok",
        "result": {
            "name": "Pearl-2-Room320B",
            "model": "Pearl-2",
            "firmware": "4.14.2",
            "serial": "DEMO0320B",
            "cpu_percent": 22.5,
            "storage_free_bytes": 400_000_000_000,
        },
    },
    "get_device_status": {
        "status": "ok",
        "result": {
            "name": "Pearl-2-Room320B",
            "model": "Pearl-2",
            "firmware": "4.14.2",
            "serial": "DEMO0320B",
            "state": "online",
            "uptime_seconds": 864_000,
        },
    },
    "get_fleet_status": {
        "status": "ok",
        "result": {"devices_total": 1, "devices_online": 1, "recorders_active": 1},
    },
}


class RoomState(BaseModel):
    """Shaped snapshot of the demo room's device + recorder state."""

    device_name: str
    model: str
    firmware: str
    state: str  # online / offline
    uptime_seconds: int
    recorder_name: str
    recorder_state: str  # recording / stopped
    duration_seconds: int
    filename: str
    cpu_percent: float
    storage_free_bytes: int
    devices_online: int
    devices_total: int
    recorders_active: int
    healthy: bool  # device online AND recorder recording
    source: str  # "mock" (vendored MCP stub) or "fallback"


class TraceEvent(BaseModel):
    """One Server-Sent Event in the demo agent trace."""

    type: str  # session_start | thought | tool_call | answer | session_complete
    data: dict[str, Any]


def _read_tool(name: str) -> dict[str, Any]:
    """Read a mock tool's canned response, preferring the vendored MCP stub."""
    try:
        from demo.mock_epiphan_mcp import call_tool_text  # repo-root demo/ package

        return json.loads(call_tool_text(name))
    except Exception:  # noqa: BLE001 — demo/ not importable in some deploys; fall back
        return _FALLBACK_TOOLS.get(name, {"status": "error", "result": {}})


def _room_snapshot() -> RoomState:
    """Build a shaped RoomState from the mock tool responses."""
    try:
        from demo.mock_epiphan_mcp import call_tool_text  # noqa: F401

        source = "mock"
    except Exception:  # noqa: BLE001
        source = "fallback"

    rec = _read_tool("get_recording_status").get("result", {})
    sysinfo = _read_tool("get_system_info").get("result", {})
    dev = _read_tool("get_device_status").get("result", {})
    fleet = _read_tool("get_fleet_status").get("result", {})

    device_state = dev.get("state", "online")
    recorder_state = rec.get("state", "stopped")
    return RoomState(
        device_name=dev.get("name") or sysinfo.get("name") or rec.get("device", "unknown"),
        model=dev.get("model") or sysinfo.get("model", "Pearl-2"),
        firmware=dev.get("firmware") or sysinfo.get("firmware", ""),
        state=device_state,
        uptime_seconds=int(dev.get("uptime_seconds", 0)),
        recorder_name=rec.get("recorder_name", ""),
        recorder_state=recorder_state,
        duration_seconds=int(rec.get("duration_seconds", 0)),
        filename=rec.get("filename", ""),
        cpu_percent=float(sysinfo.get("cpu_percent", 0.0)),
        storage_free_bytes=int(sysinfo.get("storage_free_bytes", 0)),
        devices_online=int(fleet.get("devices_online", 0)),
        devices_total=int(fleet.get("devices_total", 0)),
        recorders_active=int(fleet.get("recorders_active", 0)),
        healthy=device_state == "online" and recorder_state == "recording",
        source=source,
    )


@router.get("/room")
async def demo_room() -> RoomState:
    """Return the current mock room/device state snapshot."""
    return _room_snapshot()


def _build_trace(task: str, model: str) -> list[TraceEvent]:
    """Build the deterministic Think → Act → Observe trace for the demo task.

    Driven by the real mock tool output so the trace reflects actual device
    state (change the mock → the trace changes). Shaped to mirror the
    AgentSession / Iteration / ToolCall model the real agent produces.
    """
    rec_output = _read_tool("get_recording_status")
    rec = rec_output.get("result", {})
    recording = rec.get("state") == "recording"
    room = rec.get("device", "the room")

    if recording:
        answer = (
            f"Yes — recording is active in {room}. "
            f"'{rec.get('recorder_name', 'the recorder')}' has been running for "
            f"{int(rec.get('duration_seconds', 0)) // 60} minutes "
            f"(file: {rec.get('filename', 'n/a')})."
        )
    else:
        state = rec.get("state", "unknown")
        answer = f"No — the recorder in {room} is not currently recording (state: {state})."

    return [
        TraceEvent(type="session_start", data={"task": task, "model": model}),
        TraceEvent(
            type="thought",
            data={
                "number": 1,
                "text": (
                    f"The user is asking whether recording started in {room}. "
                    "I'll query the Pearl device's recorder status over MCP."
                ),
            },
        ),
        TraceEvent(
            type="tool_call",
            data={
                "tool_name": "get_recording_status",
                "tool_input": {},
                "tool_output": json.dumps(rec_output),
                "success": rec_output.get("status") == "ok",
                "duration_ms": 42,
            },
        ),
        TraceEvent(
            type="thought",
            data={
                "number": 2,
                "text": (
                    f"The recorder reports state='{rec.get('state', 'unknown')}'. "
                    "I have enough to answer the question directly."
                ),
            },
        ),
        TraceEvent(type="answer", data={"text": answer}),
        TraceEvent(
            type="session_complete",
            data={"status": "completed", "cost_usd": 0.0, "cloud_calls": 0, "iterations": 2},
        ),
    ]


async def _stream_trace(task: str, model: str, delay: float) -> AsyncIterator[str]:
    """Yield the demo trace as SSE frames with a small inter-event delay."""
    try:
        for event in _build_trace(task, model):
            yield f"data: {event.model_dump_json()}\n\n"
            if delay > 0:
                await asyncio.sleep(delay)
        yield "data: [DONE]\n\n"
    except Exception as exc:  # noqa: BLE001 — never break the SSE contract
        yield f"data: [ERROR] {exc}\n\n"


@router.get("/stream")
async def demo_stream(
    task: str = Query(default=DEFAULT_TASK, min_length=1),
    model: str = Query(default=DEFAULT_MODEL),
    delay: float = Query(default=0.35, ge=0.0, le=5.0),
) -> StreamingResponse:
    """Stream a Think → Act → Observe agent trace over the mock room via SSE.

        curl -N 'localhost:8787/demo/stream'
    """
    return StreamingResponse(
        _stream_trace(task, model, delay),
        media_type="text/event-stream",
        headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"},
    )
