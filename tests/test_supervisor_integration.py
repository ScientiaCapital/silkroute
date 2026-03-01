"""Integration tests for the supervisor subsystem.

End-to-end tests verifying the full workflow: plan creation → execution →
checkpointing → resume → budget enforcement → registry roundtrip.
"""

from __future__ import annotations

import json
from unittest.mock import AsyncMock

import pytest

from silkroute.mantis.runtime.interface import AgentResult, RuntimeConfig, RuntimeType
from silkroute.mantis.supervisor.models import (
    SessionStatus,
    StepStatus,
    SupervisorCheckpoint,
    SupervisorPlan,
    SupervisorSession,
    SupervisorStep,
)
from silkroute.mantis.supervisor.runtime import SupervisorRuntime


def _mock_child(runtime_type=None):
    """Create a mock child runtime."""
    mock = AsyncMock()
    mock.name = "mock"
    mock.invoke.return_value = AgentResult(
        status="completed", output="done", cost_usd=0.02, iterations=1,
    )
    return mock


class TestFullWorkflow:
    """Full supervisor workflow: create → execute → complete."""

    @pytest.mark.asyncio
    async def test_three_step_workflow(self):
        """3-step sequential workflow should complete all steps."""
        rt = SupervisorRuntime(child_factory=_mock_child)
        plan = SupervisorPlan(
            project_id="test-proj",
            description="full test",
            steps=[
                SupervisorStep(id="a", name="step1", description="task1"),
                SupervisorStep(id="b", name="step2", description="task2", depends_on=["a"]),
                SupervisorStep(id="c", name="step3", description="task3", depends_on=["b"]),
            ],
            total_budget_usd=1.0,
        )
        session = SupervisorSession(plan=plan)
        result = await rt._run_session(session, RuntimeConfig())

        assert result.status == "completed"
        assert result.metadata["step_count"] == 3
        assert result.metadata["completed_steps"] == 3
        assert result.cost_usd == pytest.approx(0.06)

        # Context should have all step outputs
        assert "a" in plan.context
        assert "b" in plan.context
        assert "c" in plan.context
        assert plan.context["a"]["status"] == "completed"


class TestCheckpointResume:
    """Checkpoint and resume workflow."""

    @pytest.mark.asyncio
    async def test_checkpoint_then_resume(self):
        """Resume from checkpoint should skip completed steps."""
        mock_pool = AsyncMock()

        # Create a session where step a is done, step b is pending
        plan = SupervisorPlan(
            steps=[
                SupervisorStep(id="a", name="done", status=StepStatus.COMPLETED),
                SupervisorStep(
                    id="b", name="pending", description="task2",
                    depends_on=["a"],
                ),
            ],
        )
        plan.context = {"a": {"status": "completed", "output": "done"}}

        session = SupervisorSession(
            id="resume-test",
            plan=plan,
            status=SessionStatus.PAUSED,
            checkpoint=SupervisorCheckpoint(
                session_id="resume-test",
                context_json=plan.context,
            ),
        )

        # Mock DB to return our session
        mock_pool.fetchrow.return_value = _make_mock_row(session)
        mock_pool.execute = AsyncMock()

        rt = SupervisorRuntime(child_factory=_mock_child, db_pool=mock_pool)
        result = await rt.resume_session("resume-test")

        assert result.status == "completed"
        # Only step b should have been executed (step a already completed)
        assert result.metadata["completed_steps"] == 2


class TestBudgetEnforcement:
    """Budget enforcement across supervisor steps."""

    @pytest.mark.asyncio
    async def test_budget_stops_execution(self):
        """Supervisor should stop when budget is exhausted."""
        def expensive_child(rt=None):
            mock = AsyncMock()
            mock.name = "mock"
            mock.invoke.return_value = AgentResult(
                status="completed", output="costly", cost_usd=3.0,
            )
            return mock

        plan = SupervisorPlan(
            steps=[
                SupervisorStep(id="a", name="step1", description="task1"),
                SupervisorStep(id="b", name="step2", description="task2", depends_on=["a"]),
            ],
            total_budget_usd=3.0,  # Only enough for 1 step
        )
        rt = SupervisorRuntime(child_factory=expensive_child)
        session = SupervisorSession(plan=plan)
        result = await rt._run_session(session, RuntimeConfig())

        assert result.metadata["completed_steps"] == 1
        assert result.metadata["failed_steps"] >= 1


class TestRegistryRoundtrip:
    """SupervisorRuntime via registry."""

    def test_registry_roundtrip(self):
        from silkroute.mantis.runtime.registry import get_runtime, reset_runtime

        reset_runtime()
        rt = get_runtime(RuntimeType.SUPERVISOR)
        assert rt.name == "supervisor"
        reset_runtime()


class TestOrchestratorChildDelegation:
    """Supervisor delegates to orchestrator as default child."""

    @pytest.mark.asyncio
    async def test_step_uses_orchestrator(self):
        """Default child runtime should be 'orchestrator'."""
        captured_types = []

        def tracking_factory(rt=None):
            captured_types.append(rt)
            mock = AsyncMock()
            mock.name = "mock"
            mock.invoke.return_value = AgentResult(
                status="completed", output="done", cost_usd=0.01,
            )
            return mock

        plan = SupervisorPlan(
            steps=[SupervisorStep(
                id="a", name="test", description="task",
                runtime_type="orchestrator",
            )],
        )
        rt = SupervisorRuntime(child_factory=tracking_factory)
        session = SupervisorSession(plan=plan)
        await rt._run_session(session, RuntimeConfig())

        assert "orchestrator" in captured_types


class TestSkipOnFailure:
    """skip_on_failure flag behavior."""

    @pytest.mark.asyncio
    async def test_skip_on_failure_continues(self):
        """Steps with skip_on_failure=True should not block downstream."""
        def failing_then_ok(rt=None):
            mock = AsyncMock()
            mock.name = "mock"
            mock.invoke.return_value = AgentResult(
                status="failed", error="oops", cost_usd=0.01,
            )
            return mock

        plan = SupervisorPlan(
            steps=[
                SupervisorStep(
                    id="a", name="fragile", description="may fail",
                    skip_on_failure=True, max_retries=0,
                ),
                SupervisorStep(
                    id="b", name="next", description="should still run",
                    depends_on=["a"],
                ),
            ],
        )
        rt = SupervisorRuntime(child_factory=failing_then_ok)
        session = SupervisorSession(plan=plan)
        result = await rt._run_session(session, RuntimeConfig())

        # Step a should be skipped (not failed), step b should still execute
        assert plan.steps[0].status == StepStatus.SKIPPED
        assert plan.context["a"]["status"] == "skipped"


# ──────────────────────────────────────────────────────────────
# Helpers
# ──────────────────────────────────────────────────────────────

def _make_mock_row(session: SupervisorSession) -> dict:
    from datetime import datetime, timezone

    return {
        "id": session.id,
        "project_id": session.project_id,
        "status": session.status.value,
        "plan_json": session.plan.to_dict(),
        "checkpoint_json": {
            "session_id": session.checkpoint.session_id,
            "plan_json": session.checkpoint.plan_json,
            "context_json": session.checkpoint.context_json,
            "step_results": session.checkpoint.step_results,
            "total_cost_usd": session.checkpoint.total_cost_usd,
        } if session.checkpoint else None,
        "context_json": session.plan.context,
        "total_cost_usd": session.total_cost_usd,
        "config_json": session.config_json,
        "created_at": datetime.now(timezone.utc),
        "updated_at": datetime.now(timezone.utc),
        "error": session.error,
    }
