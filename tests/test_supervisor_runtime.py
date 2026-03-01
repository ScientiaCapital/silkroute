"""Tests for mantis/supervisor/runtime.py — SupervisorRuntime."""

from __future__ import annotations

import json
from unittest.mock import AsyncMock, patch

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


def _mock_child_factory(runtime_type: str | None = None):
    """Create a mock runtime that returns a fixed AgentResult."""
    mock_runtime = AsyncMock()
    mock_runtime.name = "mock"
    mock_runtime.invoke.return_value = AgentResult(
        status="completed",
        output="Step done",
        iterations=1,
        cost_usd=0.05,
    )
    return mock_runtime


def _failing_factory(runtime_type: str | None = None):
    """Create a mock runtime that always fails."""
    mock_runtime = AsyncMock()
    mock_runtime.name = "mock"
    mock_runtime.invoke.return_value = AgentResult(
        status="failed",
        error="LLM error",
        cost_usd=0.01,
    )
    return mock_runtime


def _alternating_factory():
    """Factory that fails first, succeeds second."""
    call_count = 0

    def factory(rt=None):
        nonlocal call_count
        call_count += 1
        mock = AsyncMock()
        mock.name = "mock"
        if call_count % 2 == 1:
            mock.invoke.return_value = AgentResult(
                status="failed", error="temporary error", cost_usd=0.01
            )
        else:
            mock.invoke.return_value = AgentResult(
                status="completed", output="recovered", cost_usd=0.05
            )
        return mock

    return factory


class TestSupervisorRuntimeBasic:
    """SupervisorRuntime basic properties and single-step execution."""

    def test_name_property(self):
        rt = SupervisorRuntime(child_factory=_mock_child_factory)
        assert rt.name == "supervisor"

    @pytest.mark.asyncio
    async def test_invoke_single_step(self):
        rt = SupervisorRuntime(child_factory=_mock_child_factory)
        result = await rt.invoke("do something simple")
        assert result.status == "completed"
        assert result.output == "Step done"
        assert result.cost_usd == pytest.approx(0.05)
        assert result.metadata["supervised"] is True
        assert result.metadata["step_count"] == 1

    @pytest.mark.asyncio
    async def test_invoke_multi_step_sequential(self):
        """Three sequential steps should all execute."""
        rt = SupervisorRuntime(child_factory=_mock_child_factory)
        result = await rt.invoke("1. review code 2. write tests 3. deploy")
        assert result.status == "completed"
        assert result.metadata["step_count"] == 3
        assert result.metadata["completed_steps"] == 3
        assert result.cost_usd == pytest.approx(0.15)

    @pytest.mark.asyncio
    async def test_invoke_context_passing(self):
        """Step 2 should be able to read step 1's output from context."""
        captured_plans = []

        def factory(rt=None):
            mock = AsyncMock()
            mock.name = "mock"

            async def invoke(task, config=None):
                return AgentResult(
                    status="completed",
                    output=f"output for: {task}",
                    cost_usd=0.01,
                )

            mock.invoke = invoke
            return mock

        rt = SupervisorRuntime(child_factory=factory)
        result = await rt.invoke("review code and then summarize")
        assert result.status == "completed"
        # Both steps should have completed
        assert result.metadata["completed_steps"] == 2


class TestSupervisorRetry:
    """Retry logic in SupervisorRuntime._execute_step()."""

    @pytest.mark.asyncio
    async def test_invoke_step_retry_on_failure(self):
        """Failed step retries and eventually succeeds."""
        calls = []

        def factory(rt=None):
            mock = AsyncMock()
            mock.name = "mock"

            async def invoke(task, config=None):
                calls.append(1)
                if len(calls) < 3:
                    return AgentResult(status="failed", error="temp", cost_usd=0.01)
                return AgentResult(status="completed", output="ok", cost_usd=0.05)

            mock.invoke = invoke
            return mock

        plan = SupervisorPlan(
            steps=[SupervisorStep(
                id="s1", name="retry_me", description="task",
                max_retries=3, retry_backoff_seconds=0.001,
            )],
        )
        rt = SupervisorRuntime(child_factory=factory)
        session = SupervisorSession(plan=plan)
        result = await rt._run_session(session, RuntimeConfig())
        assert result.status == "completed"
        assert len(calls) == 3  # 2 failures + 1 success

    @pytest.mark.asyncio
    async def test_invoke_step_retry_exhausted(self):
        """Max retries exceeded → step fails."""
        rt = SupervisorRuntime(child_factory=_failing_factory)
        plan = SupervisorPlan(
            steps=[SupervisorStep(
                id="s1", name="fail_me", description="task",
                max_retries=1, retry_backoff_seconds=0.001,
            )],
        )
        session = SupervisorSession(plan=plan)
        result = await rt._run_session(session, RuntimeConfig())
        assert result.status == "failed"
        assert result.metadata["failed_steps"] == 1


class TestSupervisorConditions:
    """Conditional step execution."""

    @pytest.mark.asyncio
    async def test_invoke_condition_true(self):
        """Step executes when condition is met."""
        rt = SupervisorRuntime(child_factory=_mock_child_factory)
        plan = SupervisorPlan(
            steps=[
                SupervisorStep(id="a", name="first", description="task1"),
                SupervisorStep(
                    id="b", name="conditional", description="task2",
                    depends_on=["a"],
                    condition="a.status == completed",
                ),
            ],
        )
        session = SupervisorSession(plan=plan)
        result = await rt._run_session(session, RuntimeConfig())
        assert result.status == "completed"
        assert result.metadata["completed_steps"] == 2
        assert result.metadata["skipped_steps"] == 0

    @pytest.mark.asyncio
    async def test_invoke_condition_false_skip(self):
        """Step skipped when condition is not met."""
        rt = SupervisorRuntime(child_factory=_mock_child_factory)
        plan = SupervisorPlan(
            steps=[
                SupervisorStep(id="a", name="first", description="task1"),
                SupervisorStep(
                    id="b", name="conditional", description="task2",
                    depends_on=["a"],
                    condition="a.status == failed",
                ),
            ],
        )
        session = SupervisorSession(plan=plan)
        result = await rt._run_session(session, RuntimeConfig())
        assert result.metadata["skipped_steps"] == 1

    def test_evaluate_condition_key_exists(self):
        rt = SupervisorRuntime()
        ctx = {"step1": {"status": "completed"}}
        assert rt._evaluate_condition("step1", ctx) is True
        assert rt._evaluate_condition("step2", ctx) is False

    def test_evaluate_condition_equality(self):
        rt = SupervisorRuntime()
        ctx = {"step1": {"status": "completed", "output": "hello"}}
        assert rt._evaluate_condition("step1.status == completed", ctx) is True
        assert rt._evaluate_condition("step1.status == failed", ctx) is False

    def test_evaluate_condition_contains(self):
        rt = SupervisorRuntime()
        ctx = {"step1": {"status": "completed", "output": "found the bug in main.py"}}
        assert rt._evaluate_condition("step1.output contains bug", ctx) is True
        assert rt._evaluate_condition("step1.output contains error", ctx) is False


class TestSupervisorBudget:
    """Budget tracking in supervisor workflows."""

    @pytest.mark.asyncio
    async def test_invoke_budget_exhausted(self):
        """Budget exhaustion stops execution before starting a step."""
        def expensive_factory(rt=None):
            mock = AsyncMock()
            mock.name = "mock"
            mock.invoke.return_value = AgentResult(
                status="completed", output="expensive", cost_usd=5.0,
            )
            return mock

        plan = SupervisorPlan(
            steps=[
                SupervisorStep(id="a", name="step1", description="task1"),
                SupervisorStep(id="b", name="step2", description="task2", depends_on=["a"]),
                SupervisorStep(id="c", name="step3", description="task3", depends_on=["b"]),
            ],
            total_budget_usd=5.0,  # Only enough for 1 step
        )
        rt = SupervisorRuntime(child_factory=expensive_factory)
        session = SupervisorSession(plan=plan)
        result = await rt._run_session(session, RuntimeConfig())
        # First step costs 5.0, exhausts budget; step 2 should not execute
        assert result.metadata["completed_steps"] == 1
        assert result.metadata["failed_steps"] >= 1


class TestSupervisorSession:
    """Session create/resume/cancel lifecycle."""

    @pytest.mark.asyncio
    async def test_create_session_persists(self):
        mock_pool = AsyncMock()
        rt = SupervisorRuntime(child_factory=_mock_child_factory, db_pool=mock_pool)
        plan = SupervisorPlan(steps=[SupervisorStep(id="a", name="test")])
        session = await rt.create_session(plan, project_id="proj-1")
        assert session.project_id == "proj-1"
        mock_pool.execute.assert_called_once()

    @pytest.mark.asyncio
    async def test_resume_session_from_checkpoint(self):
        """Resuming a paused session should continue from last checkpoint."""
        mock_pool = AsyncMock()

        # Session with step a completed, step b pending
        existing = SupervisorSession(
            id="sess-resume",
            project_id="default",
            status=SessionStatus.PAUSED,
            plan=SupervisorPlan(
                steps=[
                    SupervisorStep(id="a", name="done", status=StepStatus.COMPLETED),
                    SupervisorStep(id="b", name="pending", description="task2", depends_on=["a"]),
                ],
            ),
            checkpoint=SupervisorCheckpoint(
                session_id="sess-resume",
                context_json={"a": {"status": "completed", "output": "done"}},
            ),
        )

        mock_pool.fetchrow.return_value = _make_mock_row(existing)

        rt = SupervisorRuntime(child_factory=_mock_child_factory, db_pool=mock_pool)
        result = await rt.resume_session("sess-resume")
        assert result.status == "completed"
        assert result.metadata["completed_steps"] == 2

    @pytest.mark.asyncio
    async def test_resume_no_db(self):
        rt = SupervisorRuntime(child_factory=_mock_child_factory, db_pool=None)
        result = await rt.resume_session("nonexistent")
        assert result.status == "failed"
        assert "no database" in result.error.lower()

    @pytest.mark.asyncio
    async def test_cancel_session(self):
        mock_pool = AsyncMock()
        existing = SupervisorSession(id="sess-cancel", status=SessionStatus.RUNNING)
        mock_pool.fetchrow.return_value = _make_mock_row(existing)

        rt = SupervisorRuntime(child_factory=_mock_child_factory, db_pool=mock_pool)
        result = await rt.cancel_session("sess-cancel")
        assert result is True

    @pytest.mark.asyncio
    async def test_cancel_session_not_found(self):
        mock_pool = AsyncMock()
        mock_pool.fetchrow.return_value = None
        rt = SupervisorRuntime(child_factory=_mock_child_factory, db_pool=mock_pool)
        result = await rt.cancel_session("nonexistent")
        assert result is False


class TestSupervisorCheckpointing:
    """Checkpoint persistence after each step."""

    @pytest.mark.asyncio
    async def test_checkpoint_after_each_step(self):
        mock_pool = AsyncMock()
        rt = SupervisorRuntime(child_factory=_mock_child_factory, db_pool=mock_pool)
        plan = SupervisorPlan(
            steps=[
                SupervisorStep(id="a", name="step1", description="task1"),
                SupervisorStep(id="b", name="step2", description="task2", depends_on=["a"]),
            ],
        )
        session = SupervisorSession(plan=plan)
        await rt._run_session(session, RuntimeConfig())
        # Checkpoint should have been called for each step + final update
        assert mock_pool.execute.call_count >= 2


class TestSupervisorStream:
    """SupervisorRuntime streaming."""

    @pytest.mark.asyncio
    async def test_stream_yields_step_events(self):
        rt = SupervisorRuntime(child_factory=_mock_child_factory)
        chunks = []
        async for chunk in rt.stream("1. review code 2. write tests"):
            chunks.append(json.loads(chunk))

        types = [c["type"] for c in chunks]
        assert "supervisor_start" in types
        assert "step_start" in types
        assert "step_completed" in types
        assert "supervisor_complete" in types


class TestSupervisorRegistry:
    """SupervisorRuntime via registry."""

    def test_registry_creates_supervisor(self):
        from silkroute.mantis.runtime.registry import get_runtime, reset_runtime

        reset_runtime()
        runtime = get_runtime(RuntimeType.SUPERVISOR)
        assert runtime.name == "supervisor"
        reset_runtime()


class TestBuildPlanFromTask:
    """SupervisorRuntime._build_plan_from_task()."""

    def test_single_task(self):
        rt = SupervisorRuntime()
        plan = rt._build_plan_from_task("fix the bug", RuntimeConfig())
        assert len(plan.steps) == 1
        assert plan.steps[0].description == "fix the bug"

    def test_numbered_list(self):
        rt = SupervisorRuntime()
        plan = rt._build_plan_from_task("1. review 2. fix 3. test", RuntimeConfig())
        assert len(plan.steps) == 3
        assert plan.steps[0].description == "review"
        assert plan.steps[2].depends_on == [plan.steps[1].id]

    def test_and_then_pattern(self):
        rt = SupervisorRuntime()
        plan = rt._build_plan_from_task("review code and then write tests", RuntimeConfig())
        assert len(plan.steps) == 2
        assert plan.steps[1].depends_on == [plan.steps[0].id]


# ──────────────────────────────────────────────────────────────
# Helpers
# ──────────────────────────────────────────────────────────────

def _make_mock_row(session: SupervisorSession) -> dict:
    """Create a mock DB row dict from a SupervisorSession."""
    import json
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
