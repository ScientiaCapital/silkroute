"""AV/edge demo endpoints — live room state + streaming agent trace.

Public (un-gated) endpoints that back the dashboard's `/demo` page. They spend
NO money — everything is served from the vendored mock epiphan MCP server
(`demo/mock_epiphan_mcp.py`), so unlike `/runtime/*` there is no `require_auth`
/ `require_not_demo` gate.

    GET /demo/room     → current mock room/device state (JSON snapshot)
    GET /demo/stream   → Server-Sent Events: a Think → Act → Observe agent trace

By default the stream is a *deterministic replay* driven by the real mock tool
outputs (`call_tool_text`), not a live LLM run — matching the self-contained-mock
philosophy of the demo (the dashboard falls back to the same narrative when the
API is unreachable) and keeping the page working with zero external deps (no
Ollama, no API key, no DB) on a fresh clone or a static Vercel deployment.

Passing `?live=true` swaps in a real `run_agent()` loop against the vendored
mock MCP server, using a local (free) Ollama model — see `_stream_live_trace`.
"""

from __future__ import annotations

import asyncio
import json
import os
import sys
from collections.abc import AsyncIterator
from pathlib import Path
from typing import Any

import structlog
from fastapi import APIRouter, Query
from fastapi.responses import StreamingResponse
from pydantic import BaseModel

log = structlog.get_logger()

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


_mock_mcp_env_ready = False


def _ensure_mock_mcp_env() -> None:
    """Point run_agent's MCP bridge at the vendored mock Epiphan server, once.

    Uses setdefault, not assignment: a real deployment's own SILKROUTE_MCP_EPIPHAN_*
    config (an actual Epiphan bridge) always wins over this demo default.
    """
    global _mock_mcp_env_ready
    if _mock_mcp_env_ready:
        return
    mock_path = Path(__file__).parent.parent.parent.parent.parent / "demo" / "mock_epiphan_mcp.py"
    os.environ.setdefault("SILKROUTE_MCP_EPIPHAN_ENABLED", "true")
    os.environ.setdefault("SILKROUTE_MCP_EPIPHAN_COMMAND", sys.executable)
    os.environ.setdefault("SILKROUTE_MCP_EPIPHAN_ARGS", json.dumps([str(mock_path)]))
    _mock_mcp_env_ready = True


# Caps concurrent live-mode streams — each one spawns a real subprocess (mock
# MCP server) + a real local model call, unlike the zero-cost scripted replay.
# This is a public, unauthenticated endpoint; the semaphore is the load-bearing
# guard against a handful of concurrent requests exhausting the local Ollama
# server / subprocess budget.
_LIVE_DEMO_SEMAPHORE = asyncio.Semaphore(2)


async def _stream_live_trace(task: str, model: str) -> AsyncIterator[str]:
    """Stream a REAL run_agent() loop against the mock room via SSE.

    Translates run_agent's stream_queue vocabulary (iteration/completed/error/
    budget_exceeded) into the dashboard's TraceEvent shapes (session_start/
    thought/tool_call/answer/session_complete). max_iterations/budget_limit_usd
    are deliberately tight — not cost guardrails (Ollama is $0) but wall-clock/
    loop-count bounds, since this is a public endpoint now spawning a real
    subprocess + model call per request instead of an in-process dict read.
    """
    from silkroute.agent.loop import run_agent

    try:
        await asyncio.wait_for(_LIVE_DEMO_SEMAPHORE.acquire(), timeout=1)
    except TimeoutError:
        yield "data: [ERROR] server busy, try again\n\n"
        return

    try:
        _ensure_mock_mcp_env()

        queue: asyncio.Queue[str | None] = asyncio.Queue(maxsize=100)
        agent_task = asyncio.create_task(
            run_agent(
                task,
                model_override=model,
                max_iterations=4,
                budget_limit_usd=0.10,
                project_id="default",  # always-seeded project; avoids an agent_sessions FK warning
                stream_queue=queue,
            )
        )

        start = TraceEvent(type="session_start", data={"task": task, "model": model, "live": True})
        yield f"data: {start.model_dump_json()}\n\n"

        reached_conclusion = False
        last_iteration = 0

        try:
            async with asyncio.timeout(120):
                while True:
                    chunk = await queue.get()
                    if chunk is None:
                        break
                    raw = json.loads(chunk)
                    event_type = raw.get("type")
                    last_iteration = raw.get("iteration", last_iteration)

                    if event_type == "iteration":
                        thought = TraceEvent(type="thought", data={"text": raw.get("thought", "")})
                        yield f"data: {thought.model_dump_json()}\n\n"
                        if raw.get("tools_called", 0) > 0:
                            tool_call = TraceEvent(
                                type="tool_call",
                                data={
                                    "count": raw["tools_called"],
                                    "cost_usd": raw.get("cost_usd", 0.0),
                                },
                            )
                            yield f"data: {tool_call.model_dump_json()}\n\n"
                    elif event_type == "completed":
                        reached_conclusion = True
                        answer = TraceEvent(
                            type="answer",
                            data={
                                "text": raw.get("output", ""),
                                "cost_usd": raw.get("cost_usd", 0.0),
                            },
                        )
                        yield f"data: {answer.model_dump_json()}\n\n"
                        complete = TraceEvent(
                            type="session_complete",
                            data={
                                "cost_usd": raw.get("cost_usd", 0.0),
                                "iterations": raw.get("iteration", 0),
                                "cloud_calls": 0,
                                "live": True,
                            },
                        )
                        yield f"data: {complete.model_dump_json()}\n\n"
                    elif event_type in ("error", "budget_exceeded"):
                        detail = raw.get("error") or raw.get("warning") or event_type
                        yield f"data: [ERROR] {detail}\n\n"
                        return

                if not reached_conclusion:
                    # run_agent hit max_iterations without ever emitting a "completed"
                    # event (the model kept calling tools without concluding) — say so
                    # honestly instead of letting the trace silently cut off with no
                    # answer bubble, which reads as broken rather than "inconclusive."
                    answer = TraceEvent(
                        type="answer",
                        data={
                            "text": (
                                "I wasn't able to reach a conclusive answer within the step "
                                "limit — the local model kept re-checking status instead of "
                                "concluding. Try again, or ask a narrower question."
                            ),
                            "cost_usd": 0.0,
                        },
                    )
                    yield f"data: {answer.model_dump_json()}\n\n"
                    complete = TraceEvent(
                        type="session_complete",
                        data={
                            "cost_usd": 0.0,
                            "iterations": last_iteration,
                            "cloud_calls": 0,
                            "live": True,
                            "inconclusive": True,
                        },
                    )
                    yield f"data: {complete.model_dump_json()}\n\n"
            yield "data: [DONE]\n\n"
        except TimeoutError:
            yield "data: [ERROR] timed out\n\n"
        except Exception as exc:  # noqa: BLE001 — never break the SSE contract
            yield f"data: [ERROR] {exc}\n\n"
        finally:
            if not agent_task.done():
                agent_task.cancel()
                # Cancelling run_agent mid-flight (e.g. on our own timeout above) can
                # unwind through the MCP stdio client's anyio task group and surface
                # as a RuntimeError ("cancel scope in a different task"), not a plain
                # CancelledError — this cleanup is best-effort at this point (the
                # client already has our [ERROR]/[DONE] frame), so swallow broadly,
                # but log it in case a real leak ever shows up here.
                #
                # Known limitation, observed on real hardware: this doesn't catch
                # every manifestation. The `mcp` package's stdio_client() spawns its
                # own anyio TaskGroup sub-tasks for the subprocess's read/write loops;
                # when cancellation lands mid-flight, one of *those* sub-tasks can end
                # up with an unretrieved exception independent of `agent_task` itself,
                # which asyncio logs directly ("Task exception was never retrieved")
                # rather than raising it here. That's an upstream mcp/anyio
                # cross-task-cancellation interaction, not something app code can
                # intercept without changing how run_agent connects to MCP servers —
                # accepted as harmless log noise on an already-degraded (timed-out)
                # request rather than chasing a fix in third-party library internals.
                try:
                    await agent_task
                except asyncio.CancelledError:
                    pass
                except Exception as cleanup_exc:  # noqa: BLE001 — see comment above
                    log.debug("live_demo_agent_cleanup_error", error=str(cleanup_exc))
    finally:
        _LIVE_DEMO_SEMAPHORE.release()


@router.get("/stream")
async def demo_stream(
    task: str = Query(default=DEFAULT_TASK, min_length=1),
    model: str = Query(default=DEFAULT_MODEL),
    delay: float = Query(default=0.35, ge=0.0, le=5.0),
    live: bool = Query(
        default=False,
        description="Run a real local-Ollama agent loop instead of the scripted replay",
    ),
) -> StreamingResponse:
    """Stream a Think → Act → Observe agent trace over the mock room via SSE.

        curl -N 'localhost:8787/demo/stream'
        curl -N 'localhost:8787/demo/stream?live=true'   # real run_agent() over local Ollama
    """
    generator = _stream_live_trace(task, model) if live else _stream_trace(task, model, delay)
    return StreamingResponse(
        generator,
        media_type="text/event-stream",
        headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"},
    )


# --- self-healing loop (GET /demo/heal) ---

# Fault types the mock can inject (mirrors demo/mock_epiphan_mcp._FAULTS).
HEAL_FAULTS = (
    "recorder_stopped",
    "signal_loss",
    "storage_full",
    "storage_unmounted",
    "device_offline",
    "cpu_overload",
)


async def _stream_heal(fault: str, delay: float) -> AsyncIterator[str]:
    """Run one detect → fix → verify cycle on the mock and stream typed frames."""
    try:
        from silkroute.autoresearch.heal import heal_with_mock

        yield f"data: {TraceEvent(type='heal_start', data={'fault': fault}).model_dump_json()}\n\n"
        if delay > 0:
            await asyncio.sleep(delay)

        result = await heal_with_mock(fault)

        for step in result.steps:
            frame = TraceEvent(type="heal_step", data={"text": step})
            yield f"data: {frame.model_dump_json()}\n\n"
            if delay > 0:
                await asyncio.sleep(delay)

        done = TraceEvent(
            type="heal_result",
            data={
                "fault_type": result.fault_type,
                "action": result.action,
                "tool_called": result.tool_called,
                "verified": result.verified,
                "outcome": result.outcome,  # healed | unhandled | healthy
            },
        )
        yield f"data: {done.model_dump_json()}\n\n"
        yield "data: [DONE]\n\n"
    except Exception as exc:  # noqa: BLE001 — never break the SSE contract
        yield f"data: [ERROR] {exc}\n\n"


@router.get("/heal")
async def demo_heal(
    fault: str = Query(default="signal_loss"),
    delay: float = Query(default=0.4, ge=0.0, le=5.0),
) -> StreamingResponse:
    """Inject a fault into the mock room and stream the self-healing loop via SSE.

        curl -N 'localhost:8787/demo/heal?fault=signal_loss'
    """
    if fault not in HEAL_FAULTS:
        fault = "signal_loss"
    return StreamingResponse(
        _stream_heal(fault, delay),
        media_type="text/event-stream",
        headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"},
    )
