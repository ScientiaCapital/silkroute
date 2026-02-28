"""Tests for mantis/orchestrator/decomposer.py — task decomposition."""

from __future__ import annotations

from silkroute.mantis.orchestrator.decomposer import (
    KeywordDecomposer,
    SingleTaskDecomposer,
    _split_compound,
)
from silkroute.mantis.runtime.interface import RuntimeConfig


class TestSplitCompound:
    """Low-level compound splitting."""

    def test_and_then_splits(self):
        parts = _split_compound("review the code and then write a summary")
        assert len(parts) == 2
        assert "review the code" in parts[0]
        assert "write a summary" in parts[1]

    def test_then_splits(self):
        parts = _split_compound("analyze the logs then fix the bug")
        assert len(parts) == 2

    def test_semicolon_then_splits(self):
        parts = _split_compound("lint the code; then run the tests")
        assert len(parts) == 2

    def test_semicolon_splits(self):
        parts = _split_compound("write tests; refactor the module; update docs")
        assert len(parts) == 3

    def test_numbered_list(self):
        task = "1. review the code 2. write tests 3. deploy"
        parts = _split_compound(task)
        assert len(parts) == 3
        assert "review" in parts[0].lower()
        assert "deploy" in parts[2].lower()

    def test_numbered_list_parenthesis(self):
        task = "1) fix bug 2) add test"
        parts = _split_compound(task)
        assert len(parts) == 2

    def test_and_splits_two_parts(self):
        parts = _split_compound("review the code and write a summary")
        assert len(parts) == 2

    def test_and_rejects_four_parts(self):
        """' and ' splitting is capped at 3 parts to avoid false positives."""
        task = "a and b and c and d"
        parts = _split_compound(task)
        # 4 parts > 3, so falls through to single task
        assert len(parts) == 1

    def test_single_task_no_split(self):
        parts = _split_compound("just review the code")
        assert len(parts) == 1
        assert parts[0] == "just review the code"

    def test_empty_string(self):
        parts = _split_compound("")
        assert len(parts) == 1

    def test_case_insensitive_markers(self):
        parts = _split_compound("Review code AND THEN write tests")
        assert len(parts) == 2


class TestKeywordDecomposer:
    """KeywordDecomposer decomposition strategy."""

    def test_compound_task_multiple_subtasks(self):
        d = KeywordDecomposer()
        plan = d.decompose("review the code and then write tests")
        assert len(plan.sub_tasks) == 2
        assert plan.parent_task == "review the code and then write tests"
        assert plan.strategy == "parallel_stages"

    def test_sequential_dependencies_for_then(self):
        """Tasks split on ' and then ' should have sequential deps."""
        d = KeywordDecomposer()
        plan = d.decompose("review the code and then write a summary")
        assert len(plan.sub_tasks) == 2
        # Second depends on first
        assert plan.sub_tasks[1].depends_on == [plan.sub_tasks[0].id]

    def test_no_dependencies_for_and(self):
        """Tasks split on ' and ' (without 'then') should be independent."""
        d = KeywordDecomposer()
        plan = d.decompose("review the code and write a summary")
        assert len(plan.sub_tasks) == 2
        assert plan.sub_tasks[0].depends_on == []
        assert plan.sub_tasks[1].depends_on == []

    def test_tier_classification(self):
        d = KeywordDecomposer()
        plan = d.decompose("summarize the README and then implement the feature")
        tiers = [st.tier_hint for st in plan.sub_tasks]
        assert tiers[0] == "free"  # "summarize" is a free trigger
        assert tiers[1] == "standard"  # "implement" is a standard trigger

    def test_single_task_passthrough(self):
        d = KeywordDecomposer()
        plan = d.decompose("fix the login bug")
        assert len(plan.sub_tasks) == 1
        assert plan.strategy == "single"

    def test_config_propagation(self):
        d = KeywordDecomposer()
        cfg = RuntimeConfig(max_iterations=10, budget_limit_usd=5.0)
        plan = d.decompose("review code and fix bugs", cfg)
        assert plan.total_budget_usd == 5.0
        for st in plan.sub_tasks:
            assert st.max_iterations == 10

    def test_priority_decreasing(self):
        """Earlier sub-tasks should have higher priority."""
        d = KeywordDecomposer()
        plan = d.decompose("1. first 2. second 3. third")
        priorities = [st.priority for st in plan.sub_tasks]
        assert priorities == sorted(priorities, reverse=True)


class TestSingleTaskDecomposer:
    """SingleTaskDecomposer pass-through."""

    def test_always_single_subtask(self):
        d = SingleTaskDecomposer()
        plan = d.decompose("review the code and then write tests and fix bugs")
        assert len(plan.sub_tasks) == 1
        assert plan.strategy == "single"

    def test_budget_from_config(self):
        d = SingleTaskDecomposer()
        cfg = RuntimeConfig(budget_limit_usd=3.0)
        plan = d.decompose("fix bugs", cfg)
        assert plan.sub_tasks[0].budget_usd == 3.0
        assert plan.total_budget_usd == 3.0

    def test_classification_applied(self):
        d = SingleTaskDecomposer()
        plan = d.decompose("summarize the README")
        assert plan.sub_tasks[0].tier_hint == "free"
