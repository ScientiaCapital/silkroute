"""Tests for LLMDecomposer."""

from __future__ import annotations

from collections import OrderedDict
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from silkroute.mantis.orchestrator.llm_decomposer import LLMDecomposer
from silkroute.mantis.orchestrator.models import OrchestrationPlan, SubTask
from silkroute.mantis.runtime.interface import RuntimeConfig


# ============================================================================
# Helpers
# ============================================================================


def _make_llm_response(sub_tasks: list[dict]) -> MagicMock:
    """Build a mock LLM response object."""
    import json

    content = json.dumps({"sub_tasks": sub_tasks})
    response = MagicMock()
    response.content = content
    return response


def _make_llm_factory(response_content: str) -> MagicMock:
    """Return a factory callable that produces a mock LLM."""
    llm = AsyncMock()
    mock_response = MagicMock()
    mock_response.content = response_content
    llm.ainvoke = AsyncMock(return_value=mock_response)

    def factory(model_id: str) -> AsyncMock:
        return llm

    return factory


# ============================================================================
# _parse_response
# ============================================================================


class TestParseResponse:
    def test_parse_valid_json_single_task(self):
        decomp = LLMDecomposer()
        cfg = RuntimeConfig()
        content = '{"sub_tasks": [{"description": "Write hello world", "tier_hint": "free", "depends_on": []}]}'
        plan = decomp._parse_response(content, "Write hello world", cfg)

        assert isinstance(plan, OrchestrationPlan)
        assert len(plan.sub_tasks) == 1
        assert plan.sub_tasks[0].description == "Write hello world"
        assert plan.sub_tasks[0].tier_hint == "free"
        assert plan.strategy == "single"

    def test_parse_valid_json_multiple_tasks(self):
        decomp = LLMDecomposer()
        cfg = RuntimeConfig()
        content = '{"sub_tasks": [{"description": "Task A", "tier_hint": "standard", "depends_on": []}, {"description": "Task B", "tier_hint": "premium", "depends_on": [0]}]}'
        plan = decomp._parse_response(content, "Do Task A and then Task B", cfg)

        assert len(plan.sub_tasks) == 2
        assert plan.strategy == "parallel_stages"
        # Task B depends on Task A's ID
        assert plan.sub_tasks[1].depends_on == [plan.sub_tasks[0].id]

    def test_parse_markdown_fenced_json(self):
        """LLM may wrap JSON in markdown code fences."""
        decomp = LLMDecomposer()
        cfg = RuntimeConfig()
        content = (
            "Here is the decomposition:\n"
            "```json\n"
            '{"sub_tasks": [{"description": "Fenced task", "tier_hint": "free", "depends_on": []}]}\n'
            "```"
        )
        plan = decomp._parse_response(content, "Fenced task", cfg)
        assert len(plan.sub_tasks) == 1
        assert plan.sub_tasks[0].description == "Fenced task"

    def test_parse_depends_on_index_mapping(self):
        """depends_on integers map to actual sub-task IDs."""
        decomp = LLMDecomposer()
        cfg = RuntimeConfig()
        content = """{
            "sub_tasks": [
                {"description": "Step 1", "tier_hint": "free", "depends_on": []},
                {"description": "Step 2", "tier_hint": "standard", "depends_on": [0]},
                {"description": "Step 3", "tier_hint": "premium", "depends_on": [1]}
            ]
        }"""
        plan = decomp._parse_response(content, "Three steps", cfg)
        assert len(plan.sub_tasks) == 3
        st1, st2, st3 = plan.sub_tasks
        assert st2.depends_on == [st1.id]
        assert st3.depends_on == [st2.id]

    def test_parse_caps_at_5_sub_tasks(self):
        """LLM responses with >5 sub-tasks are capped at 5."""
        decomp = LLMDecomposer()
        cfg = RuntimeConfig()
        sub_tasks = [
            {"description": f"Task {i}", "tier_hint": "free", "depends_on": []}
            for i in range(8)
        ]
        import json

        content = json.dumps({"sub_tasks": sub_tasks})
        plan = decomp._parse_response(content, "Many tasks", cfg)
        assert len(plan.sub_tasks) == 5

    def test_parse_raises_on_no_json(self):
        decomp = LLMDecomposer()
        cfg = RuntimeConfig()
        with pytest.raises(ValueError, match="No JSON found"):
            decomp._parse_response("This is not JSON at all.", "task", cfg)

    def test_parse_raises_on_empty_sub_tasks(self):
        decomp = LLMDecomposer()
        cfg = RuntimeConfig()
        with pytest.raises(ValueError, match="Empty sub_tasks"):
            decomp._parse_response('{"sub_tasks": []}', "task", cfg)


# ============================================================================
# Caching
# ============================================================================


class TestLLMDecomposerCache:
    def test_cache_hit_returns_same_plan(self):
        """Same task returns same cached plan without calling LLM."""
        factory_calls: list[str] = []

        def factory(model_id: str) -> AsyncMock:
            llm = AsyncMock()
            llm.ainvoke = AsyncMock(return_value=_make_llm_response([
                {"description": "Do something", "tier_hint": "free", "depends_on": []}
            ]))
            factory_calls.append(model_id)
            return llm

        decomp = LLMDecomposer(llm_factory=factory)

        # First call — should call LLM
        task = "Write a simple hello-world function"
        plan1 = decomp.decompose(task)

        # Second call — should hit cache
        plan2 = decomp.decompose(task)

        assert plan1 is plan2  # Same object from cache
        assert len(factory_calls) == 1  # LLM called exactly once

    def test_cache_lru_eviction(self):
        """When cache exceeds maxsize, the oldest entry is evicted."""
        call_count = 0

        def factory(model_id: str) -> AsyncMock:
            nonlocal call_count
            call_count += 1
            llm = AsyncMock()
            llm.ainvoke = AsyncMock(return_value=_make_llm_response([
                {"description": f"Task {call_count}", "tier_hint": "free", "depends_on": []}
            ]))
            return llm

        decomp = LLMDecomposer(llm_factory=factory, cache_maxsize=3)

        # Fill cache to capacity
        tasks = [f"unique task number {i}" for i in range(4)]
        for t in tasks:
            decomp.decompose(t)

        # Cache should hold at most 3 entries
        assert len(decomp._cache) == 3
        # The first task (tasks[0]) should have been evicted
        first_key = decomp._cache_key(tasks[0])
        assert first_key not in decomp._cache

    def test_different_tasks_different_cache_keys(self):
        decomp = LLMDecomposer()
        key1 = decomp._cache_key("task one")
        key2 = decomp._cache_key("task two")
        assert key1 != key2

    def test_same_task_same_cache_key(self):
        decomp = LLMDecomposer()
        task = "exactly the same task string"
        assert decomp._cache_key(task) == decomp._cache_key(task)


# ============================================================================
# Fallback
# ============================================================================


class TestLLMDecomposerFallback:
    def test_fallback_on_network_error(self):
        """If LLM raises any exception, KeywordDecomposer is used instead."""
        def factory(model_id: str) -> AsyncMock:
            llm = AsyncMock()
            llm.ainvoke = AsyncMock(side_effect=ConnectionError("network down"))
            return llm

        decomp = LLMDecomposer(llm_factory=factory)
        plan = decomp.decompose("Write tests and then run them")

        # Fallback should produce a valid plan
        assert isinstance(plan, OrchestrationPlan)
        assert len(plan.sub_tasks) >= 1

    def test_fallback_on_invalid_response(self):
        """If LLM returns unparseable content, fallback is used."""
        def factory(model_id: str) -> AsyncMock:
            llm = AsyncMock()
            mock_resp = MagicMock()
            mock_resp.content = "I cannot decompose this task."
            llm.ainvoke = AsyncMock(return_value=mock_resp)
            return llm

        decomp = LLMDecomposer(llm_factory=factory)
        plan = decomp.decompose("Write tests")

        assert isinstance(plan, OrchestrationPlan)
        assert len(plan.sub_tasks) >= 1


# ============================================================================
# Full decompose with mock LLM
# ============================================================================


class TestLLMDecomposerDecompose:
    def test_decompose_single_task(self):
        """Simple task returns a single-element plan."""
        def factory(model_id: str) -> AsyncMock:
            llm = AsyncMock()
            llm.ainvoke = AsyncMock(return_value=_make_llm_response([
                {"description": "List all files", "tier_hint": "free", "depends_on": []}
            ]))
            return llm

        decomp = LLMDecomposer(llm_factory=factory)
        plan = decomp.decompose("List all files in the project")

        assert isinstance(plan, OrchestrationPlan)
        assert len(plan.sub_tasks) == 1
        assert plan.strategy == "single"

    def test_decompose_compound_task(self):
        """Compound task returns multi-step plan."""
        def factory(model_id: str) -> AsyncMock:
            llm = AsyncMock()
            llm.ainvoke = AsyncMock(return_value=_make_llm_response([
                {"description": "Analyze codebase", "tier_hint": "premium", "depends_on": []},
                {"description": "Write report", "tier_hint": "standard", "depends_on": [0]},
            ]))
            return llm

        decomp = LLMDecomposer(llm_factory=factory)
        plan = decomp.decompose("Analyze the codebase then write a report")

        assert len(plan.sub_tasks) == 2
        assert plan.strategy == "parallel_stages"
        # Dependency wired correctly
        assert plan.sub_tasks[1].depends_on == [plan.sub_tasks[0].id]

    def test_decompose_with_openrouter_mock(self):
        """Test that create_openrouter_model is called when no factory given.

        create_openrouter_model is imported lazily inside _async_llm_decompose,
        so we patch at the source module (silkroute.providers.openrouter).
        """
        mock_llm = AsyncMock()
        mock_llm.ainvoke = AsyncMock(return_value=_make_llm_response([
            {"description": "Do something", "tier_hint": "free", "depends_on": []}
        ]))

        with patch(
            "silkroute.mantis.orchestrator.llm_decomposer.create_openrouter_model",
            return_value=mock_llm,
            create=True,
        ):
            decomp = LLMDecomposer()
            plan = decomp.decompose("Do something simple")

        assert isinstance(plan, OrchestrationPlan)

    def test_decompose_uses_runtime_config(self):
        """RuntimeConfig budget is propagated to the plan."""
        def factory(model_id: str) -> AsyncMock:
            llm = AsyncMock()
            llm.ainvoke = AsyncMock(return_value=_make_llm_response([
                {"description": "Task", "tier_hint": "standard", "depends_on": []}
            ]))
            return llm

        decomp = LLMDecomposer(llm_factory=factory)
        cfg = RuntimeConfig(budget_limit_usd=42.0)
        plan = decomp.decompose("Do a task", config=cfg)

        assert plan.total_budget_usd == 42.0


# ============================================================================
# OrchestratorRuntime integration
# ============================================================================


class TestOrchestratorRuntimeUseLLMDecomposer:
    def test_use_llm_decomposer_flag_sets_llm_decomposer(self):
        from silkroute.mantis.orchestrator.llm_decomposer import LLMDecomposer as LLMDec
        from silkroute.mantis.orchestrator.runtime import OrchestratorRuntime

        rt = OrchestratorRuntime(use_llm_decomposer=True)
        assert isinstance(rt._decomposer, LLMDec)

    def test_explicit_decomposer_overrides_flag(self):
        from silkroute.mantis.orchestrator.decomposer import KeywordDecomposer
        from silkroute.mantis.orchestrator.runtime import OrchestratorRuntime

        kd = KeywordDecomposer()
        rt = OrchestratorRuntime(decomposer=kd, use_llm_decomposer=True)
        # Explicit decomposer wins
        assert rt._decomposer is kd

    def test_default_uses_keyword_decomposer(self):
        from silkroute.mantis.orchestrator.decomposer import KeywordDecomposer
        from silkroute.mantis.orchestrator.runtime import OrchestratorRuntime

        rt = OrchestratorRuntime()
        assert isinstance(rt._decomposer, KeywordDecomposer)


# ============================================================================
# LLMDecomposer exported from __init__
# ============================================================================


class TestLLMDecomposerExport:
    def test_llm_decomposer_exported_from_orchestrator(self):
        from silkroute.mantis.orchestrator import LLMDecomposer as Exported

        assert Exported is LLMDecomposer
