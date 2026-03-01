"""Tests for mantis/supervisor/models.py — supervisor data models."""

from __future__ import annotations

import pytest

from silkroute.mantis.supervisor.models import (
    SessionStatus,
    StepStatus,
    SupervisorCheckpoint,
    SupervisorPlan,
    SupervisorSession,
    SupervisorStep,
)


class TestEnums:
    """SessionStatus and StepStatus enum values."""

    def test_session_statuses(self):
        assert SessionStatus.PENDING == "pending"
        assert SessionStatus.RUNNING == "running"
        assert SessionStatus.PAUSED == "paused"
        assert SessionStatus.COMPLETED == "completed"
        assert SessionStatus.FAILED == "failed"
        assert SessionStatus.CANCELLED == "cancelled"

    def test_step_statuses(self):
        assert StepStatus.PENDING == "pending"
        assert StepStatus.RUNNING == "running"
        assert StepStatus.COMPLETED == "completed"
        assert StepStatus.FAILED == "failed"
        assert StepStatus.SKIPPED == "skipped"


class TestSupervisorStep:
    """SupervisorStep defaults and fields."""

    def test_defaults(self):
        step = SupervisorStep()
        assert step.name == ""
        assert step.status == StepStatus.PENDING
        assert step.runtime_type == "orchestrator"
        assert step.max_retries == 2
        assert step.retry_count == 0
        assert step.retry_backoff_seconds == 5.0
        assert step.condition is None
        assert step.skip_on_failure is False
        assert step.cost_usd == 0.0

    def test_custom_values(self):
        step = SupervisorStep(
            name="review",
            description="Review the code",
            max_retries=5,
            condition="step1.status == completed",
        )
        assert step.name == "review"
        assert step.description == "Review the code"
        assert step.max_retries == 5
        assert step.condition == "step1.status == completed"


class TestSupervisorPlan:
    """SupervisorPlan navigation and status derivation."""

    def test_empty_plan_is_complete(self):
        plan = SupervisorPlan()
        assert plan.is_complete is True
        assert plan.overall_status == SessionStatus.COMPLETED

    def test_next_pending_step_returns_first(self):
        plan = SupervisorPlan(steps=[
            SupervisorStep(id="a", name="step1"),
            SupervisorStep(id="b", name="step2"),
        ])
        step = plan.next_pending_step()
        assert step is not None
        assert step.id == "a"

    def test_next_pending_step_respects_depends_on(self):
        plan = SupervisorPlan(steps=[
            SupervisorStep(id="a", name="step1"),
            SupervisorStep(id="b", name="step2", depends_on=["a"]),
        ])
        # Step b depends on a, which is pending — only a is available
        step = plan.next_pending_step()
        assert step is not None
        assert step.id == "a"

    def test_next_pending_step_after_completion(self):
        plan = SupervisorPlan(steps=[
            SupervisorStep(id="a", name="step1", status=StepStatus.COMPLETED),
            SupervisorStep(id="b", name="step2", depends_on=["a"]),
        ])
        step = plan.next_pending_step()
        assert step is not None
        assert step.id == "b"

    def test_next_pending_step_none_when_all_complete(self):
        plan = SupervisorPlan(steps=[
            SupervisorStep(id="a", status=StepStatus.COMPLETED),
            SupervisorStep(id="b", status=StepStatus.COMPLETED),
        ])
        assert plan.next_pending_step() is None

    def test_next_pending_step_unblocked_by_failed(self):
        """A step depending on a failed step should still be available."""
        plan = SupervisorPlan(steps=[
            SupervisorStep(id="a", status=StepStatus.FAILED),
            SupervisorStep(id="b", depends_on=["a"]),
        ])
        step = plan.next_pending_step()
        assert step is not None
        assert step.id == "b"

    def test_is_complete_all_terminal(self):
        plan = SupervisorPlan(steps=[
            SupervisorStep(id="a", status=StepStatus.COMPLETED),
            SupervisorStep(id="b", status=StepStatus.SKIPPED),
            SupervisorStep(id="c", status=StepStatus.FAILED),
        ])
        assert plan.is_complete is True

    def test_is_complete_not_all_terminal(self):
        plan = SupervisorPlan(steps=[
            SupervisorStep(id="a", status=StepStatus.COMPLETED),
            SupervisorStep(id="b", status=StepStatus.PENDING),
        ])
        assert plan.is_complete is False

    def test_overall_status_pending(self):
        plan = SupervisorPlan(steps=[
            SupervisorStep(id="a", status=StepStatus.PENDING),
            SupervisorStep(id="b", status=StepStatus.PENDING),
        ])
        assert plan.overall_status == SessionStatus.PENDING

    def test_overall_status_running(self):
        plan = SupervisorPlan(steps=[
            SupervisorStep(id="a", status=StepStatus.RUNNING),
            SupervisorStep(id="b", status=StepStatus.PENDING),
        ])
        assert plan.overall_status == SessionStatus.RUNNING

    def test_overall_status_completed(self):
        plan = SupervisorPlan(steps=[
            SupervisorStep(id="a", status=StepStatus.COMPLETED),
            SupervisorStep(id="b", status=StepStatus.COMPLETED),
        ])
        assert plan.overall_status == SessionStatus.COMPLETED

    def test_overall_status_failed_all(self):
        plan = SupervisorPlan(steps=[
            SupervisorStep(id="a", status=StepStatus.FAILED),
            SupervisorStep(id="b", status=StepStatus.SKIPPED),
        ])
        assert plan.overall_status == SessionStatus.FAILED

    def test_overall_status_mixed_returns_completed(self):
        """Mix of completed and failed steps = completed (best-effort)."""
        plan = SupervisorPlan(steps=[
            SupervisorStep(id="a", status=StepStatus.COMPLETED),
            SupervisorStep(id="b", status=StepStatus.FAILED),
        ])
        assert plan.overall_status == SessionStatus.COMPLETED


class TestPlanSerialization:
    """SupervisorPlan to_dict / from_dict roundtrip."""

    def test_roundtrip(self):
        plan = SupervisorPlan(
            id="plan-1",
            project_id="proj-1",
            description="test plan",
            total_budget_usd=5.0,
            steps=[
                SupervisorStep(id="a", name="step1", description="do thing"),
                SupervisorStep(id="b", name="step2", depends_on=["a"]),
            ],
        )
        data = plan.to_dict()
        restored = SupervisorPlan.from_dict(data)

        assert restored.id == "plan-1"
        assert restored.project_id == "proj-1"
        assert restored.description == "test plan"
        assert restored.total_budget_usd == 5.0
        assert len(restored.steps) == 2
        assert restored.steps[0].id == "a"
        assert restored.steps[1].depends_on == ["a"]

    def test_from_dict_with_status(self):
        data = {
            "id": "p1",
            "steps": [
                {"id": "a", "status": "completed"},
                {"id": "b", "status": "failed"},
            ],
        }
        plan = SupervisorPlan.from_dict(data)
        assert plan.steps[0].status == StepStatus.COMPLETED
        assert plan.steps[1].status == StepStatus.FAILED


class TestSupervisorCheckpoint:
    """SupervisorCheckpoint creation."""

    def test_defaults(self):
        cp = SupervisorCheckpoint(session_id="sess-1")
        assert cp.session_id == "sess-1"
        assert cp.total_cost_usd == 0.0
        assert cp.plan_json == {}
        assert cp.context_json == {}


class TestSupervisorSession:
    """SupervisorSession creation and defaults."""

    def test_defaults(self):
        session = SupervisorSession()
        assert session.status == SessionStatus.PENDING
        assert session.total_cost_usd == 0.0
        assert session.error == ""
        assert session.checkpoint is None

    def test_with_plan(self):
        plan = SupervisorPlan(steps=[SupervisorStep(id="a", name="test")])
        session = SupervisorSession(
            id="sess-1",
            project_id="proj-1",
            plan=plan,
        )
        assert session.plan.steps[0].name == "test"
        assert session.project_id == "proj-1"
