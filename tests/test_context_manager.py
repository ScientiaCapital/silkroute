"""Tests for mantis/context/manager.py — ContextManager."""

from __future__ import annotations

import pytest

from silkroute.mantis.context.manager import ContextManager
from silkroute.mantis.context.models import ContextEntry, ContextScope, ContextSnapshot


class TestContextManagerSetGet:
    """set() and get() basic behavior."""

    async def test_set_and_get(self) -> None:
        mgr = ContextManager()
        await mgr.set("my_key", "my_value", ContextScope.PLAN)
        entry = mgr.get("my_key")
        assert entry is not None
        assert entry.key == "my_key"
        assert entry.value == "my_value"
        assert entry.scope == ContextScope.PLAN

    async def test_get_missing_returns_none(self) -> None:
        mgr = ContextManager()
        assert mgr.get("nonexistent") is None

    async def test_set_with_source(self) -> None:
        mgr = ContextManager()
        await mgr.set("result", "data", ContextScope.STEP, source="step_1")
        entry = mgr.get("result")
        assert entry is not None
        assert entry.source == "step_1"

    async def test_set_with_token_estimate(self) -> None:
        mgr = ContextManager()
        await mgr.set("big_entry", "lots of data", ContextScope.SESSION, token_estimate=500)
        assert mgr._total_tokens == 500


class TestContextManagerVersioning:
    """Version increments on update."""

    async def test_initial_version_is_1(self) -> None:
        mgr = ContextManager()
        await mgr.set("k", "v", ContextScope.PLAN)
        entry = mgr.get("k")
        assert entry is not None
        assert entry.version == 1

    async def test_version_increments_on_update(self) -> None:
        mgr = ContextManager()
        await mgr.set("k", "v1", ContextScope.PLAN)
        await mgr.set("k", "v2", ContextScope.PLAN)
        entry = mgr.get("k")
        assert entry is not None
        assert entry.version == 2
        assert entry.value == "v2"

    async def test_multiple_updates_increment_each_time(self) -> None:
        mgr = ContextManager()
        for i in range(5):
            await mgr.set("k", f"v{i}", ContextScope.PLAN)
        entry = mgr.get("k")
        assert entry is not None
        assert entry.version == 5


class TestGetForStep:
    """get_for_step() scope filtering."""

    async def test_plan_scoped_included(self) -> None:
        mgr = ContextManager()
        await mgr.set("plan_key", "plan_value", ContextScope.PLAN, source="system")
        result = mgr.get_for_step("step_1")
        assert "plan_key" in result
        assert result["plan_key"] == "plan_value"

    async def test_session_scoped_included(self) -> None:
        mgr = ContextManager()
        await mgr.set("sess_key", "sess_value", ContextScope.SESSION)
        result = mgr.get_for_step("step_2")
        assert "sess_key" in result

    async def test_step_scoped_matching_source_included(self) -> None:
        mgr = ContextManager()
        await mgr.set("step_output", "data", ContextScope.STEP, source="step_1")
        result = mgr.get_for_step("step_1")
        assert "step_output" in result

    async def test_step_scoped_different_source_excluded(self) -> None:
        mgr = ContextManager()
        await mgr.set("other_output", "data", ContextScope.STEP, source="step_2")
        result = mgr.get_for_step("step_1")
        assert "other_output" not in result

    async def test_mixed_scopes(self) -> None:
        mgr = ContextManager()
        await mgr.set("plan_k", "plan_v", ContextScope.PLAN)
        await mgr.set("step_k", "step_v", ContextScope.STEP, source="step_A")
        await mgr.set("other_k", "other_v", ContextScope.STEP, source="step_B")
        await mgr.set("sess_k", "sess_v", ContextScope.SESSION)

        result = mgr.get_for_step("step_A")
        assert "plan_k" in result
        assert "sess_k" in result
        assert "step_k" in result
        assert "other_k" not in result


class TestSnapshotRestore:
    """snapshot() and restore() roundtrip."""

    async def test_snapshot_roundtrip(self) -> None:
        mgr = ContextManager()
        await mgr.set("a", 1, ContextScope.PLAN, token_estimate=10)
        await mgr.set("b", "hello", ContextScope.STEP, source="step_1", token_estimate=20)

        snap = mgr.snapshot()
        assert snap.total_tokens == 30
        assert "a" in snap.entries
        assert "b" in snap.entries

        # Restore into a fresh manager
        mgr2 = ContextManager()
        mgr2.restore(snap)
        assert mgr2.get("a") is not None
        assert mgr2.get("a").value == 1  # type: ignore[union-attr]
        assert mgr2._total_tokens == 30

    async def test_restore_replaces_existing(self) -> None:
        mgr = ContextManager()
        await mgr.set("old", "data", ContextScope.PLAN)

        snap = ContextSnapshot(entries={}, total_tokens=0)
        mgr.restore(snap)

        assert mgr.get("old") is None
        assert mgr._total_tokens == 0


class TestLegacyDictRoundtrip:
    """to_legacy_dict() and from_legacy_dict() roundtrip."""

    async def test_to_legacy_dict_contains_values(self) -> None:
        mgr = ContextManager()
        await mgr.set("result", "output", ContextScope.PLAN)
        d = mgr.to_legacy_dict()
        assert d["result"] == "output"
        assert "__silkroute_context_meta__" in d

    async def test_from_legacy_dict_roundtrip(self) -> None:
        mgr = ContextManager()
        await mgr.set("x", 42, ContextScope.PLAN, source="user", token_estimate=5)
        await mgr.set("y", "hello", ContextScope.STEP, source="step_1", token_estimate=3)

        d = mgr.to_legacy_dict()
        mgr2 = ContextManager.from_legacy_dict(d)

        entry_x = mgr2.get("x")
        entry_y = mgr2.get("y")
        assert entry_x is not None
        assert entry_x.value == 42
        assert entry_x.source == "user"
        assert entry_x.scope == ContextScope.PLAN

        assert entry_y is not None
        assert entry_y.value == "hello"
        assert entry_y.scope == ContextScope.STEP

    async def test_from_legacy_dict_plain_dict(self) -> None:
        """from_legacy_dict handles plain dicts without meta key."""
        plain = {"step_1": {"output": "data"}, "step_2": {"output": "more"}}
        mgr = ContextManager.from_legacy_dict(plain)
        assert mgr.get("step_1") is not None
        assert mgr.get("step_2") is not None
        assert mgr.get("step_1").value == {"output": "data"}  # type: ignore[union-attr]


class TestTokenTracking:
    """Token tracking and STEP eviction on overflow."""

    async def test_token_tracking(self) -> None:
        mgr = ContextManager()
        await mgr.set("a", "v", ContextScope.PLAN, token_estimate=100)
        await mgr.set("b", "v", ContextScope.SESSION, token_estimate=200)
        assert mgr._total_tokens == 300

    async def test_update_adjusts_token_count(self) -> None:
        mgr = ContextManager()
        await mgr.set("a", "v1", ContextScope.PLAN, token_estimate=100)
        await mgr.set("a", "v2", ContextScope.PLAN, token_estimate=50)
        assert mgr._total_tokens == 50

    async def test_step_eviction_on_overflow(self) -> None:
        # max_tokens=100; add STEP entry with 60 tokens, then another with 60 tokens
        mgr = ContextManager(max_tokens=100)
        await mgr.set("plan_key", "plan_data", ContextScope.PLAN, token_estimate=30)
        await mgr.set("step_key_1", "step_data_1", ContextScope.STEP, source="step_1", token_estimate=60)
        # Now at 90 tokens — under budget

        # Adding a second STEP entry (60 tokens) causes overflow -> evict step_key_1
        await mgr.set("step_key_2", "step_data_2", ContextScope.STEP, source="step_2", token_estimate=60)

        # plan_key (PLAN-scoped) should NOT be evicted
        assert mgr.get("plan_key") is not None
        # step_key_1 should have been evicted
        assert mgr.get("step_key_1") is None
        # step_key_2 is newest so it stays
        assert mgr.get("step_key_2") is not None
