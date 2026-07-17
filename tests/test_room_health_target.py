"""Tests for the room-health autoresearch target (self-healing playbook)."""

from __future__ import annotations

import shutil
from pathlib import Path

import pytest

from silkroute.autoresearch.targets.base import ResearchTarget
from silkroute.autoresearch.targets.room_health import RoomHealthTarget

REPO_ROOT = Path(__file__).resolve().parent.parent
SCENARIOS = REPO_ROOT / "demo" / "room_health" / "fault_scenarios.json"

# A correct, well-ordered playbook — specific causes before general ones — that
# remediates every fault scenario without over-firing on the healthy room.
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


def _target_with_playbook(tmp_path: Path, playbook: str) -> RoomHealthTarget:
    """Build a target rooted at tmp_path with the real scenarios + a given playbook."""
    room = tmp_path / "demo" / "room_health"
    room.mkdir(parents=True)
    shutil.copy(SCENARIOS, room / "fault_scenarios.json")
    (room / "remediation_rules.yaml").write_text(playbook)
    return RoomHealthTarget(tmp_path)


class TestProtocol:
    def test_conforms_to_research_target(self) -> None:
        t = RoomHealthTarget(REPO_ROOT)
        assert isinstance(t, ResearchTarget)
        # The engine also calls get_editable_files() (not in the Protocol).
        assert hasattr(t, "get_editable_files")

    def test_editable_files_is_only_the_playbook(self) -> None:
        t = RoomHealthTarget(REPO_ROOT)
        files = t.get_editable_files()
        assert [f.name for f in files] == ["remediation_rules.yaml"]
        # Scenarios must NOT be editable — that would be editing the test.
        assert not any("fault_scenarios" in str(f) for f in files)


class TestEvaluation:
    @pytest.mark.asyncio
    async def test_seed_playbook_is_partial(self) -> None:
        # The shipped seed intentionally leaves faults unhandled.
        m = await RoomHealthTarget(REPO_ROOT).evaluate()
        assert m.lint_clean is True
        assert 0.0 < m.pass_rate < 1.0
        assert m.total_tests == 9

    @pytest.mark.asyncio
    async def test_complete_playbook_scores_perfect(self, tmp_path: Path) -> None:
        m = await _target_with_playbook(tmp_path, COMPLETE_PLAYBOOK).evaluate()
        assert m.pass_rate == 1.0
        assert m.coverage_pct == 1.0
        assert m.lint_clean is True
        assert m.score == pytest.approx(1.0)

    @pytest.mark.asyncio
    async def test_complete_beats_seed(self, tmp_path: Path) -> None:
        seed = await RoomHealthTarget(REPO_ROOT).evaluate()
        complete = await _target_with_playbook(tmp_path, COMPLETE_PLAYBOOK).evaluate()
        # A better playbook must score higher — this is what drives KEEP.
        assert complete.is_better_than(seed)

    @pytest.mark.asyncio
    async def test_unknown_action_is_lint_dirty(self, tmp_path: Path) -> None:
        bad = "rules:\n  - id: x\n    when: {device_state: offline}\n    action: teleport\n"
        m = await _target_with_playbook(tmp_path, bad).evaluate()
        assert m.lint_clean is False

    @pytest.mark.asyncio
    async def test_malformed_yaml_is_lint_dirty(self, tmp_path: Path) -> None:
        m = await _target_with_playbook(tmp_path, "rules: [ - broken: :\n").evaluate()
        assert m.lint_clean is False

    @pytest.mark.asyncio
    async def test_over_broad_rule_fails_healthy_room(self, tmp_path: Path) -> None:
        # A rule that fires on any online device "remediates" a healthy room.
        overbroad = (
            "rules:\n  - id: greedy\n    when: {device_state: online}\n"
            "    action: start_recorder\n"
        )
        m = await _target_with_playbook(tmp_path, overbroad).evaluate()
        assert "healthy" in m.error_summary


class TestContext:
    @pytest.mark.asyncio
    async def test_context_lists_unhandled_faults(self) -> None:
        ctx = await RoomHealthTarget(REPO_ROOT).build_context(recent_entries=[])
        assert "Faults NOT yet remediated" in ctx
        # The seed doesn't handle cpu overload — the context should surface it.
        assert "cpu_overload" in ctx

    @pytest.mark.asyncio
    async def test_context_includes_recent_history(self) -> None:
        entries = [{"status": "keep", "score": 0.8, "description": "added cpu rule"}]
        ctx = await RoomHealthTarget(REPO_ROOT).build_context(recent_entries=entries)
        assert "Recent Experiments" in ctx
        assert "added cpu rule" in ctx
