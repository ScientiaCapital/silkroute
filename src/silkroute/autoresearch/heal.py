"""Room-health remediation executor — the runtime counterpart to the target.

Closes the self-healing loop: given a (mock) room, read its signals, ask the
SAME playbook the autoresearch target optimizes which remediation to apply, call
the corresponding MCP **action** tool, then re-read and verify the room is
healthy again. Detect → fix → verify.

- ``read_signals`` flattens the mock's read-tool JSON into the 6-signal dict the
  playbook engine expects.
- ``heal_room`` runs one detect → decide → act → verify cycle against a connected
  ``ToolRegistry`` and returns a structured ``HealResult``. Honest: if the current
  playbook has no rule for the fault, it reports the fault detected but
  ``verified=False`` — the playbook score made tangible.
- ``heal_with_mock`` spawns the vendored mock with an injected fault, connects the
  MCP bridge with an allowlist that includes the action tools (the production
  epiphan allowlist stays read-only), runs one cycle, and tears down.
"""

from __future__ import annotations

import json
import os
import sys
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from silkroute.agent.tools import ToolRegistry
from silkroute.autoresearch.playbook import KNOWN_ACTIONS, decide_action, load_playbook
from silkroute.mcp_bridge.client import connect_mcp_server

_REPO_ROOT = Path(__file__).resolve().parents[3]
DEFAULT_MOCK_PATH = _REPO_ROOT / "demo" / "mock_epiphan_mcp.py"
DEFAULT_PLAYBOOK_PATH = _REPO_ROOT / "demo" / "room_health" / "remediation_rules.yaml"

# Read tools the executor needs + all remediation action tools. This is the
# allowlist passed to the mock ONLY — never the production epiphan default.
_READ_TOOLS = ["get_device_status", "get_recording_status", "get_system_info"]
_ACTION_TOOLS = sorted(KNOWN_ACTIONS - {"none"})
HEAL_ALLOWLIST = _READ_TOOLS + _ACTION_TOOLS

# Known fault types, checked in priority order (device-level first). Mirrors the
# fault-scenario fixtures; used to name the detected fault independent of the
# playbook (so an unhandled fault is still *detected*).
_HEALTHY = {
    "device_state": "online",
    "recorder_state": "recording",
    "input_has_signal": True,
    "storage_mounted": True,
}


@dataclass
class HealResult:
    """Outcome of one detect → fix → verify cycle."""

    before: dict[str, Any]
    fault_type: str | None          # None = room was already healthy
    action: str                     # remediation the playbook chose ("none" if unhandled)
    tool_called: bool
    after: dict[str, Any] | None
    verified: bool                  # room healthy after the action
    outcome: str                    # "healed" | "unhandled" | "healthy"
    steps: list[str] = field(default_factory=list)


def _parse(text: str) -> dict[str, Any]:
    """Parse a tool's JSON text output; {} on error/non-JSON."""
    try:
        parsed = json.loads(text)
        return parsed if isinstance(parsed, dict) else {}
    except (json.JSONDecodeError, TypeError):
        return {}


async def read_signals(registry: ToolRegistry) -> dict[str, Any]:
    """Read the room's current state and flatten to the 6 playbook signals."""
    dev = _parse(await registry.execute("get_device_status", {})).get("result", {})
    rec = _parse(await registry.execute("get_recording_status", {})).get("result", {})
    sysinfo = _parse(await registry.execute("get_system_info", {})).get("result", {})
    return {
        "device_state": dev.get("state", "online"),
        "recorder_state": rec.get("state", "recording"),
        "input_has_signal": dev.get("input_has_signal", True),
        "storage_mounted": sysinfo.get("storage_mounted", True),
        "storage_percent_used": sysinfo.get("storage_percent_used", 0),
        "cpu_percent": sysinfo.get("cpu_percent", 0.0),
    }


def detect_fault(signals: dict[str, Any]) -> str | None:
    """Ground-truth fault detector (independent of the playbook). None = healthy."""
    if signals["device_state"] != "online":
        return "device_offline"
    if not signals["storage_mounted"]:
        return "storage_unmounted"
    if signals["storage_percent_used"] >= 90:
        return "storage_full"
    if not signals["input_has_signal"]:
        return "signal_loss"
    if signals["cpu_percent"] >= 90:
        return "cpu_overload"
    if signals["recorder_state"] != "recording":
        return "recorder_stopped"
    return None


async def heal_room(
    registry: ToolRegistry, playbook_path: Path = DEFAULT_PLAYBOOK_PATH
) -> HealResult:
    """Run one detect → decide → act → verify cycle against a connected registry."""
    before = await read_signals(registry)
    fault_type = detect_fault(before)
    steps = [f"read state → fault: {fault_type or 'none (healthy)'}"]

    if fault_type is None:
        steps.append("no remediation needed")
        return HealResult(before, None, "none", False, None, True, "healthy", steps)

    rules, _lint_clean, _err = load_playbook(playbook_path)
    action = decide_action(rules, before)
    steps.append(f"playbook chose: {action}")

    if action == "none":
        # Faulted, but the current playbook has no rule for it.
        steps.append("playbook has no remediation for this fault → unhandled")
        return HealResult(before, fault_type, "none", False, None, False, "unhandled", steps)

    await registry.execute(action, {})
    steps.append(f"applied action tool: {action}()")
    after = await read_signals(registry)
    verified = detect_fault(after) is None
    outcome = "healed" if verified else "unhandled"
    steps.append(f"re-read state → {'VERIFIED healthy' if verified else 'still faulted'}")
    return HealResult(before, fault_type, action, True, after, verified, outcome, steps)


async def heal_with_mock(
    fault: str | None,
    *,
    playbook_path: Path = DEFAULT_PLAYBOOK_PATH,
    mock_path: Path = DEFAULT_MOCK_PATH,
) -> HealResult:
    """Spawn the mock with an injected fault, run one heal cycle, tear down."""
    registry = ToolRegistry()
    env = {**os.environ, "SILKROUTE_MOCK_ROOM_FAULT": fault or ""}
    stack = await connect_mcp_server(
        registry,
        command=sys.executable,
        args=[str(mock_path)],
        env=env,
        tool_allowlist=HEAL_ALLOWLIST,
    )
    if stack is None:
        raise RuntimeError("failed to connect the mock epiphan MCP server")
    try:
        return await heal_room(registry, playbook_path)
    finally:
        await stack.aclose()
