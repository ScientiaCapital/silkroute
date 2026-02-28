"""Tests for mantis/orchestrator/models.py — data models and topological sort."""

from __future__ import annotations

import pytest

from silkroute.mantis.orchestrator.models import (
    OrchestrationPlan,
    OrchestrationResult,
    SubAgentResult,
    SubTask,
)
from silkroute.mantis.runtime.interface import AgentResult, RuntimeType


class TestSubTask:
    """SubTask dataclass basics."""

    def test_defaults(self):
        st = SubTask()
        assert st.description == ""
        assert st.runtime_type == RuntimeType.LEGACY
        assert st.tier_hint == "standard"
        assert st.depends_on == []
        assert st.budget_usd == 1.0
        assert st.max_iterations == 25
        assert st.priority == 0
        assert len(st.id) == 8

    def test_unique_ids(self):
        ids = {SubTask().id for _ in range(50)}
        assert len(ids) == 50

    def test_custom_values(self):
        st = SubTask(
            id="abc",
            parent_task="parent",
            description="do stuff",
            runtime_type=RuntimeType.DEEP_AGENTS,
            tier_hint="premium",
            depends_on=["xyz"],
            budget_usd=5.0,
            max_iterations=10,
            priority=3,
            metadata={"key": "val"},
        )
        assert st.id == "abc"
        assert st.parent_task == "parent"
        assert st.runtime_type == RuntimeType.DEEP_AGENTS
        assert st.depends_on == ["xyz"]
        assert st.metadata == {"key": "val"}


class TestOrchestrationPlan:
    """OrchestrationPlan including topological sort via stages."""

    def test_empty_plan(self):
        plan = OrchestrationPlan()
        assert plan.stages == []
        assert plan.sub_tasks == []

    def test_single_task_one_stage(self):
        plan = OrchestrationPlan(sub_tasks=[SubTask(id="a")])
        stages = plan.stages
        assert len(stages) == 1
        assert len(stages[0]) == 1
        assert stages[0][0].id == "a"

    def test_independent_tasks_single_stage(self):
        """Tasks with no dependencies should all be in one stage."""
        plan = OrchestrationPlan(
            sub_tasks=[SubTask(id="a"), SubTask(id="b"), SubTask(id="c")]
        )
        stages = plan.stages
        assert len(stages) == 1
        assert len(stages[0]) == 3

    def test_linear_chain_three_stages(self):
        """a -> b -> c should produce 3 sequential stages."""
        plan = OrchestrationPlan(
            sub_tasks=[
                SubTask(id="a"),
                SubTask(id="b", depends_on=["a"]),
                SubTask(id="c", depends_on=["b"]),
            ]
        )
        stages = plan.stages
        assert len(stages) == 3
        assert stages[0][0].id == "a"
        assert stages[1][0].id == "b"
        assert stages[2][0].id == "c"

    def test_diamond_dependency(self):
        """Diamond: a -> (b, c) -> d should produce 3 stages."""
        plan = OrchestrationPlan(
            sub_tasks=[
                SubTask(id="a"),
                SubTask(id="b", depends_on=["a"]),
                SubTask(id="c", depends_on=["a"]),
                SubTask(id="d", depends_on=["b", "c"]),
            ]
        )
        stages = plan.stages
        assert len(stages) == 3
        assert stages[0][0].id == "a"
        # Stage 2 has b and c in parallel
        stage2_ids = {t.id for t in stages[1]}
        assert stage2_ids == {"b", "c"}
        assert stages[2][0].id == "d"

    def test_cycle_detection(self):
        plan = OrchestrationPlan(
            sub_tasks=[
                SubTask(id="a", depends_on=["b"]),
                SubTask(id="b", depends_on=["a"]),
            ]
        )
        with pytest.raises(ValueError, match="cycle"):
            plan.stages  # noqa: B018

    def test_invalid_dependency_ignored(self):
        """Dependencies on non-existent task IDs are silently skipped."""
        plan = OrchestrationPlan(
            sub_tasks=[SubTask(id="a", depends_on=["nonexistent"])]
        )
        stages = plan.stages
        assert len(stages) == 1
        assert stages[0][0].id == "a"

    def test_priority_ordering_within_stage(self):
        """Higher priority tasks should appear first within a stage."""
        plan = OrchestrationPlan(
            sub_tasks=[
                SubTask(id="low", priority=1),
                SubTask(id="high", priority=10),
                SubTask(id="mid", priority=5),
            ]
        )
        stages = plan.stages
        assert len(stages) == 1
        ids = [t.id for t in stages[0]]
        assert ids == ["high", "mid", "low"]

    def test_plan_defaults(self):
        plan = OrchestrationPlan()
        assert plan.parent_task == ""
        assert plan.strategy == "parallel_stages"
        assert plan.total_budget_usd == 10.0


class TestSubAgentResult:
    """SubAgentResult dataclass."""

    def test_defaults(self):
        r = SubAgentResult(agent_result=AgentResult(status="pending"))
        assert r.sub_task_id == ""
        assert r.stage == 0
        assert r.elapsed_ms == 0
        assert r.agent_result.status == "pending"

    def test_with_agent_result(self):
        ar = AgentResult(status="completed", cost_usd=0.05, iterations=3)
        r = SubAgentResult(sub_task_id="abc", agent_result=ar, stage=1, elapsed_ms=500)
        assert r.agent_result.success
        assert r.elapsed_ms == 500


class TestOrchestrationResult:
    """OrchestrationResult dataclass."""

    def test_defaults(self):
        r = OrchestrationResult()
        assert r.status == "completed"
        assert r.sub_results == []
        assert r.total_cost_usd == 0.0
        assert r.merged_output == ""
        assert r.plan is None

    def test_with_sub_results(self):
        sr = SubAgentResult(
            sub_task_id="a",
            agent_result=AgentResult(status="completed", cost_usd=0.1),
        )
        r = OrchestrationResult(
            sub_results=[sr],
            total_cost_usd=0.1,
            total_iterations=5,
            merged_output="done",
        )
        assert len(r.sub_results) == 1
        assert r.total_cost_usd == 0.1
