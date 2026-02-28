"""Tests for mantis/orchestrator/middleware.py, budget.py, and aggregator.py."""

from __future__ import annotations

import asyncio

import pytest

from silkroute.mantis.orchestrator.aggregator import aggregate_results
from silkroute.mantis.orchestrator.budget import (
    BudgetExhaustedError,
    BudgetTracker,
    allocate_budget,
)
from silkroute.mantis.orchestrator.middleware import (
    BudgetMiddleware,
    LoggingMiddleware,
    MiddlewareContext,
    ValidationMiddleware,
)
from silkroute.mantis.orchestrator.models import (
    OrchestrationPlan,
    SubAgentResult,
    SubTask,
)
from silkroute.mantis.runtime.interface import AgentResult, RuntimeConfig

# ──────────────────────────────────────────────────────────────
# BudgetTracker tests
# ──────────────────────────────────────────────────────────────


class TestBudgetTracker:
    """BudgetTracker spend tracking and reservation."""

    async def test_initial_state(self):
        t = BudgetTracker(total_usd=5.0)
        assert t.remaining_usd == 5.0
        assert t.spent_usd == 0.0

    async def test_record_spend(self):
        t = BudgetTracker(total_usd=5.0)
        await t.record_spend(2.0)
        assert t.spent_usd == 2.0
        assert t.remaining_usd == 3.0

    async def test_record_spend_over_total(self):
        t = BudgetTracker(total_usd=1.0)
        await t.record_spend(1.5)
        assert t.spent_usd == 1.5
        assert t.remaining_usd == 0.0  # Clamped to 0

    async def test_try_reserve_success(self):
        t = BudgetTracker(total_usd=5.0)
        assert await t.try_reserve(3.0) is True
        assert t.spent_usd == 3.0

    async def test_try_reserve_failure(self):
        t = BudgetTracker(total_usd=1.0)
        assert await t.try_reserve(2.0) is False
        assert t.spent_usd == 0.0  # No change on failure

    async def test_concurrent_record_spend(self):
        """Concurrent spend recording should be safe."""
        t = BudgetTracker(total_usd=100.0)
        tasks = [t.record_spend(0.1) for _ in range(100)]
        await asyncio.gather(*tasks)
        assert abs(t.spent_usd - 10.0) < 0.001

    async def test_concurrent_try_reserve(self):
        """Concurrent reservations should not exceed total."""
        t = BudgetTracker(total_usd=1.0)
        results = await asyncio.gather(*[t.try_reserve(0.3) for _ in range(5)])
        successes = sum(1 for r in results if r)
        assert successes == 3  # 3 * 0.3 = 0.9 <= 1.0, 4th would be 1.2 > 1.0


# ──────────────────────────────────────────────────────────────
# allocate_budget tests
# ──────────────────────────────────────────────────────────────


class TestAllocateBudget:
    """Budget allocation by tier weight."""

    def test_empty_plan(self):
        plan = OrchestrationPlan(total_budget_usd=10.0)
        result = allocate_budget(plan)
        assert result.sub_tasks == []

    def test_proportional_by_tier(self):
        plan = OrchestrationPlan(
            total_budget_usd=10.0,
            sub_tasks=[
                SubTask(id="free", tier_hint="free"),     # weight 0.5
                SubTask(id="std", tier_hint="standard"),  # weight 2.0
                SubTask(id="prem", tier_hint="premium"),  # weight 5.0
            ],
        )
        result = allocate_budget(plan)
        budgets = {st.id: st.budget_usd for st in result.sub_tasks}
        # Available = 10 * 0.9 = 9.0, total_weight = 7.5
        assert budgets["free"] == pytest.approx(0.6, abs=0.01)
        assert budgets["std"] == pytest.approx(2.4, abs=0.01)
        assert budgets["prem"] == pytest.approx(6.0, abs=0.01)

    def test_floor_budget(self):
        plan = OrchestrationPlan(
            total_budget_usd=0.01,
            sub_tasks=[SubTask(id="a", tier_hint="free")],
        )
        result = allocate_budget(plan)
        assert result.sub_tasks[0].budget_usd >= 0.01

    def test_equal_tiers(self):
        plan = OrchestrationPlan(
            total_budget_usd=4.0,
            sub_tasks=[
                SubTask(id="a", tier_hint="standard"),
                SubTask(id="b", tier_hint="standard"),
            ],
        )
        result = allocate_budget(plan)
        # 4.0 * 0.9 / 2 = 1.8 each
        assert result.sub_tasks[0].budget_usd == pytest.approx(1.8, abs=0.01)
        assert result.sub_tasks[1].budget_usd == pytest.approx(1.8, abs=0.01)


# ──────────────────────────────────────────────────────────────
# ValidationMiddleware tests
# ──────────────────────────────────────────────────────────────


class TestValidationMiddleware:
    """ValidationMiddleware rejects bad sub-task configs."""

    async def test_valid_passes(self):
        mw = ValidationMiddleware()
        ctx = MiddlewareContext(
            sub_task=SubTask(max_iterations=5, budget_usd=1.0),
            config=RuntimeConfig(),
        )
        result = await mw.before(ctx)
        assert result is ctx

    async def test_zero_iterations_rejected(self):
        mw = ValidationMiddleware()
        ctx = MiddlewareContext(
            sub_task=SubTask(max_iterations=0, budget_usd=1.0),
            config=RuntimeConfig(),
        )
        with pytest.raises(ValueError, match="max_iterations"):
            await mw.before(ctx)

    async def test_zero_budget_rejected(self):
        mw = ValidationMiddleware()
        ctx = MiddlewareContext(
            sub_task=SubTask(max_iterations=5, budget_usd=0),
            config=RuntimeConfig(),
        )
        with pytest.raises(ValueError, match="budget_usd"):
            await mw.before(ctx)

    async def test_after_passthrough(self):
        mw = ValidationMiddleware()
        ctx = MiddlewareContext(sub_task=SubTask(), config=RuntimeConfig())
        result = AgentResult(status="completed")
        assert await mw.after(ctx, result) is result


# ──────────────────────────────────────────────────────────────
# BudgetMiddleware tests
# ──────────────────────────────────────────────────────────────


class TestBudgetMiddleware:
    """BudgetMiddleware enforces budget and records spend."""

    async def test_caps_budget_to_remaining(self):
        tracker = BudgetTracker(total_usd=1.0)
        mw = BudgetMiddleware(tracker)
        ctx = MiddlewareContext(
            sub_task=SubTask(budget_usd=5.0),
            config=RuntimeConfig(),
        )
        result = await mw.before(ctx)
        assert result.sub_task.budget_usd == 1.0

    async def test_exhausted_raises(self):
        tracker = BudgetTracker(total_usd=0.0)
        mw = BudgetMiddleware(tracker)
        ctx = MiddlewareContext(
            sub_task=SubTask(budget_usd=1.0),
            config=RuntimeConfig(),
        )
        with pytest.raises(BudgetExhaustedError):
            await mw.before(ctx)

    async def test_after_records_spend(self):
        tracker = BudgetTracker(total_usd=10.0)
        mw = BudgetMiddleware(tracker)
        ctx = MiddlewareContext(sub_task=SubTask(), config=RuntimeConfig())
        result = AgentResult(status="completed", cost_usd=0.5)
        await mw.after(ctx, result)
        assert tracker.spent_usd == 0.5


# ──────────────────────────────────────────────────────────────
# LoggingMiddleware tests
# ──────────────────────────────────────────────────────────────


class TestLoggingMiddleware:
    """LoggingMiddleware emits structlog events."""

    async def test_before_returns_ctx(self):
        mw = LoggingMiddleware()
        ctx = MiddlewareContext(sub_task=SubTask(id="abc"), config=RuntimeConfig())
        assert await mw.before(ctx) is ctx

    async def test_after_returns_result(self):
        mw = LoggingMiddleware()
        ctx = MiddlewareContext(sub_task=SubTask(id="abc"), config=RuntimeConfig())
        result = AgentResult(status="completed")
        assert await mw.after(ctx, result) is result


# ──────────────────────────────────────────────────────────────
# Middleware chain ordering
# ──────────────────────────────────────────────────────────────


class TestMiddlewareChain:
    """Middleware chain runs in correct order."""

    async def test_chain_order(self):
        """Validate → Budget → Logging chain order."""
        tracker = BudgetTracker(total_usd=10.0)
        chain = [
            ValidationMiddleware(),
            BudgetMiddleware(tracker),
            LoggingMiddleware(),
        ]

        ctx = MiddlewareContext(
            sub_task=SubTask(budget_usd=2.0, max_iterations=5),
            config=RuntimeConfig(),
            stage=1,
        )

        for mw in chain:
            ctx = await mw.before(ctx)

        # Budget should be capped
        assert ctx.budget_remaining_usd == 10.0

        result = AgentResult(status="completed", cost_usd=1.5)
        for mw in reversed(chain):
            result = await mw.after(ctx, result)

        assert tracker.spent_usd == 1.5

    async def test_chain_stops_on_validation_error(self):
        """Chain should stop if validation fails."""
        tracker = BudgetTracker(total_usd=10.0)
        chain = [
            ValidationMiddleware(),
            BudgetMiddleware(tracker),
        ]

        ctx = MiddlewareContext(
            sub_task=SubTask(budget_usd=1.0, max_iterations=0),
            config=RuntimeConfig(),
        )

        with pytest.raises(ValueError):
            for mw in chain:
                ctx = await mw.before(ctx)


# ──────────────────────────────────────────────────────────────
# aggregate_results tests
# ──────────────────────────────────────────────────────────────


class TestAggregateResults:
    """Result aggregation into OrchestrationResult."""

    def _make_sub_result(
        self,
        sub_id: str = "a",
        status: str = "completed",
        cost: float = 0.1,
        output: str = "done",
        iterations: int = 3,
    ) -> SubAgentResult:
        return SubAgentResult(
            sub_task_id=sub_id,
            agent_result=AgentResult(
                status=status,
                cost_usd=cost,
                output=output,
                iterations=iterations,
            ),
        )

    def test_empty_results(self):
        plan = OrchestrationPlan()
        tracker = BudgetTracker(total_usd=5.0)
        result = aggregate_results([], plan, tracker)
        assert result.status == "completed"
        assert result.merged_output == ""
        assert result.total_cost_usd == 0.0

    def test_all_completed(self):
        plan = OrchestrationPlan()
        tracker = BudgetTracker(total_usd=5.0)
        subs = [
            self._make_sub_result("a", cost=0.1, output="result A"),
            self._make_sub_result("b", cost=0.2, output="result B"),
        ]
        result = aggregate_results(subs, plan, tracker)
        assert result.status == "completed"
        assert result.total_cost_usd == pytest.approx(0.3)
        assert result.total_iterations == 6
        assert "result A" in result.merged_output
        assert "result B" in result.merged_output

    def test_partial_failure(self):
        plan = OrchestrationPlan()
        tracker = BudgetTracker(total_usd=5.0)
        subs = [
            self._make_sub_result("a", status="completed"),
            self._make_sub_result("b", status="failed", output=""),
        ]
        result = aggregate_results(subs, plan, tracker)
        assert result.status == "partial_failure"

    def test_all_failed(self):
        plan = OrchestrationPlan()
        tracker = BudgetTracker(total_usd=5.0)
        subs = [
            self._make_sub_result("a", status="failed", output=""),
            self._make_sub_result("b", status="timeout", output=""),
        ]
        result = aggregate_results(subs, plan, tracker)
        assert result.status == "failed"

    def test_empty_outputs_skipped(self):
        plan = OrchestrationPlan()
        tracker = BudgetTracker(total_usd=5.0)
        subs = [
            self._make_sub_result("a", output="hello"),
            self._make_sub_result("b", output=""),
        ]
        result = aggregate_results(subs, plan, tracker)
        assert result.merged_output == "hello"

    def test_plan_reference(self):
        plan = OrchestrationPlan(parent_task="test task")
        tracker = BudgetTracker(total_usd=5.0)
        result = aggregate_results([], plan, tracker)
        assert result.plan is plan
        assert result.plan.parent_task == "test task"
