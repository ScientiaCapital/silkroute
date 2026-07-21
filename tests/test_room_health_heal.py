"""Tests for the self-healing loop: mock action tools + heal executor."""

from __future__ import annotations

from collections.abc import Iterator
from pathlib import Path
from typing import Any

import pytest

from demo import mock_epiphan_mcp as mock
from silkroute.autoresearch.heal import (
    DEFAULT_PLAYBOOK_PATH,
    HEAL_ALLOWLIST,
    heal_room,
    heal_with_mock,
)
from silkroute.config.settings import MCPConfig

# The ORIGINAL intentionally-incomplete seed playbook (6/9 scenarios), frozen as a
# fixture. The live playbook (DEFAULT_PLAYBOOK_PATH) has since been evolved to 9/9
# (PR #1), so tests about seed behavior must use this frozen copy.
SEED_PLAYBOOK_PATH = Path(__file__).resolve().parent / "fixtures" / "seed_remediation_rules.yaml"

COMPLETE_PLAYBOOK = """\
rules:
  - id: device-offline
    when: {device_state: offline}
    action: reboot_device
  - id: storage-unmounted
    when: {storage_mounted: false}
    action: remount_storage
  - id: storage-full
    when: {storage_percent_used: {gte: 90}}
    action: rotate_recordings
  - id: cpu-overload
    when: {cpu_percent: {gte: 90}}
    action: throttle_channels
  - id: input-signal-loss
    when: {input_has_signal: false}
    action: restart_input
  - id: recorder-not-recording
    when: {device_state: online, recorder_state: {ne: recording}}
    action: start_recorder
"""


@pytest.fixture(autouse=True)
def _reset_room() -> Iterator[None]:
    """Keep the module-global mock room isolated between tests."""
    mock.reset_room()
    yield
    mock.reset_room()


class _InProcRegistry:
    """A ToolRegistry stand-in that drives the in-process mock (no subprocess)."""

    async def execute(self, name: str, arguments: dict[str, Any]) -> str:
        return mock.call_tool_text(name, arguments)


# --- mock action tools ---


class TestMockActions:
    def test_fault_injection_breaks_a_signal(self) -> None:
        import json

        mock.reset_room("signal_loss")
        dev = json.loads(mock.call_tool_text("get_device_status"))["result"]
        assert dev["input_has_signal"] is False

    def test_action_mutates_state(self) -> None:
        import json

        mock.reset_room("recorder_stopped")

        def rec_state() -> str:
            return json.loads(mock.call_tool_text("get_recording_status"))["result"]["state"]

        assert rec_state() == "stopped"
        assert json.loads(mock.call_tool_text("start_recorder"))["status"] == "ok"
        assert rec_state() == "recording"

    def test_thirteen_tools_served(self) -> None:
        assert len(mock.list_tool_names()) == 13  # 7 read + 6 action


# --- heal executor ---


class TestHealExecutor:
    @pytest.mark.asyncio
    @pytest.mark.parametrize("fault", ["recorder_stopped", "signal_loss", "storage_full"])
    async def test_seed_handles_these_faults(self, fault: str) -> None:
        mock.reset_room(fault)
        result = await heal_room(_InProcRegistry(), SEED_PLAYBOOK_PATH)
        assert result.fault_type == fault
        assert result.outcome == "healed"
        assert result.verified is True
        assert result.tool_called is True

    @pytest.mark.asyncio
    @pytest.mark.parametrize("fault", ["storage_unmounted", "device_offline", "cpu_overload"])
    async def test_seed_leaves_these_unhandled(self, fault: str) -> None:
        # The frozen seed playbook has no rule for these — detected, not fixed.
        mock.reset_room(fault)
        result = await heal_room(_InProcRegistry(), SEED_PLAYBOOK_PATH)
        assert result.fault_type == fault
        assert result.outcome == "unhandled"
        assert result.verified is False

    @pytest.mark.asyncio
    @pytest.mark.parametrize(
        "fault",
        ["recorder_stopped", "signal_loss", "storage_full",
         "storage_unmounted", "device_offline", "cpu_overload"],
    )
    async def test_live_playbook_heals_every_fault(self, fault: str) -> None:
        # The SHIPPED playbook was evolved to full coverage (PR #1) — every
        # injectable fault must now heal end-to-end. Pin the new truth.
        mock.reset_room(fault)
        result = await heal_room(_InProcRegistry(), DEFAULT_PLAYBOOK_PATH)
        assert result.fault_type == fault
        assert result.outcome == "healed"
        assert result.verified is True

    @pytest.mark.asyncio
    async def test_healthy_room_needs_no_action(self) -> None:
        mock.reset_room(None)
        result = await heal_room(_InProcRegistry(), DEFAULT_PLAYBOOK_PATH)
        assert result.fault_type is None
        assert result.outcome == "healthy"
        assert result.tool_called is False

    @pytest.mark.asyncio
    @pytest.mark.parametrize(
        "fault",
        ["recorder_stopped", "signal_loss", "storage_full",
         "storage_unmounted", "device_offline", "cpu_overload"],
    )
    async def test_complete_playbook_heals_everything(self, fault: str, tmp_path: Path) -> None:
        playbook = tmp_path / "complete.yaml"
        playbook.write_text(COMPLETE_PLAYBOOK)
        mock.reset_room(fault)
        result = await heal_room(_InProcRegistry(), playbook)
        assert result.outcome == "healed"
        assert result.verified is True


class TestHealWithMock:
    @pytest.mark.asyncio
    async def test_end_to_end_via_subprocess_bridge(self, tmp_path: Path) -> None:
        # Exercises the real MCP subprocess bridge + action tools.
        playbook = tmp_path / "complete.yaml"
        playbook.write_text(COMPLETE_PLAYBOOK)
        result = await heal_with_mock("device_offline", playbook_path=playbook)
        assert result.fault_type == "device_offline"
        assert result.action == "reboot_device"
        assert result.verified is True


class TestSecurityPosture:
    def test_production_allowlist_has_no_action_tools(self) -> None:
        # Action tools must NEVER be in the production epiphan default allowlist.
        prod = set(MCPConfig().epiphan_tool_allowlist)
        actions = {
            "start_recorder", "restart_input", "rotate_recordings",
            "remount_storage", "reboot_device", "throttle_channels",
        }
        assert prod.isdisjoint(actions)

    def test_heal_allowlist_includes_actions(self) -> None:
        assert "reboot_device" in HEAL_ALLOWLIST
        assert "get_device_status" in HEAL_ALLOWLIST
