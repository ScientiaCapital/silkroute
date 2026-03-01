"""Tests for mantis/orchestrator/middleware.py, budget.py, and aggregator.py."""

from __future__ import annotations

import asyncio
import time

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

    async def test_reserves_budget_atomically(self):
        tracker = BudgetTracker(total_usd=5.0)
        mw = BudgetMiddleware(tracker)
        ctx = MiddlewareContext(
            sub_task=SubTask(budget_usd=3.0),
            config=RuntimeConfig(),
        )
        result = await mw.before(ctx)
        # Budget should be reserved (spent_usd increases by budget_usd)
        assert tracker.spent_usd == 3.0
        assert result.budget_remaining_usd == 2.0

    async def test_exhausted_raises(self):
        tracker = BudgetTracker(total_usd=0.0)
        mw = BudgetMiddleware(tracker)
        ctx = MiddlewareContext(
            sub_task=SubTask(budget_usd=1.0),
            config=RuntimeConfig(),
        )
        with pytest.raises(BudgetExhaustedError):
            await mw.before(ctx)

    async def test_after_settles_spend(self):
        tracker = BudgetTracker(total_usd=10.0)
        mw = BudgetMiddleware(tracker)
        ctx = MiddlewareContext(sub_task=SubTask(budget_usd=2.0), config=RuntimeConfig())
        # Simulate before() reservation
        await mw.before(ctx)
        assert tracker.spent_usd == 2.0
        # After settles: reserved 2.0 but actual cost 0.5 → release 1.5
        result = AgentResult(status="completed", cost_usd=0.5)
        await mw.after(ctx, result)
        assert tracker.spent_usd == pytest.approx(0.5)


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

        # Budget reserved: 2.0 spent, 8.0 remaining
        assert ctx.budget_remaining_usd == 8.0
        assert tracker.spent_usd == 2.0

        # After: settle reserved=2.0, actual=1.5
        result = AgentResult(status="completed", cost_usd=1.5)
        for mw in reversed(chain):
            result = await mw.after(ctx, result)

        assert tracker.spent_usd == pytest.approx(1.5)

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


# ──────────────────────────────────────────────────────────────
# Phase 4: settle(), immutable allocate, new middleware tests
# ──────────────────────────────────────────────────────────────

from silkroute.mantis.orchestrator.middleware import (
    AlertMiddleware,
    AlertThresholds,
    CheckpointMiddleware,
    RetryConfig,
    RetryMiddleware,
)


class TestBudgetSettle:
    """BudgetTracker.settle() releases over-reservation."""

    async def test_settle_releases_unused(self):
        t = BudgetTracker(total_usd=10.0)
        await t.try_reserve(5.0)
        assert t.spent_usd == 5.0
        await t.settle(5.0, 2.0)
        assert t.spent_usd == pytest.approx(2.0)

    async def test_settle_exact_match(self):
        t = BudgetTracker(total_usd=10.0)
        await t.try_reserve(3.0)
        await t.settle(3.0, 3.0)
        assert t.spent_usd == pytest.approx(3.0)


class TestAllocateBudgetImmutable:
    """W3: allocate_budget() must not mutate original plan."""

    def test_original_plan_unchanged(self):
        plan = OrchestrationPlan(
            total_budget_usd=10.0,
            sub_tasks=[
                SubTask(id="a", tier_hint="standard", budget_usd=1.0),
                SubTask(id="b", tier_hint="premium", budget_usd=1.0),
            ],
        )
        original_a_budget = plan.sub_tasks[0].budget_usd
        result = allocate_budget(plan)
        # Original plan is untouched
        assert plan.sub_tasks[0].budget_usd == original_a_budget
        # Result has different budgets
        assert result.sub_tasks[0].budget_usd != original_a_budget


class TestRetryMiddleware:
    """RetryMiddleware injects config into context."""

    async def test_retry_config_injected(self):
        mw = RetryMiddleware(RetryConfig(max_retries=5))
        ctx = MiddlewareContext(sub_task=SubTask(), config=RuntimeConfig())
        result_ctx = await mw.before(ctx)
        assert "retry_config" in result_ctx.metadata
        assert result_ctx.metadata["retry_config"].max_retries == 5

    async def test_retry_default_values(self):
        mw = RetryMiddleware()
        ctx = MiddlewareContext(sub_task=SubTask(), config=RuntimeConfig())
        result_ctx = await mw.before(ctx)
        rc = result_ctx.metadata["retry_config"]
        assert rc.max_retries == 3
        assert rc.backoff_base == 1.0
        assert rc.backoff_factor == 2.0
        assert "failed" in rc.retryable_statuses

    async def test_after_passthrough(self):
        mw = RetryMiddleware()
        ctx = MiddlewareContext(sub_task=SubTask(), config=RuntimeConfig())
        result = AgentResult(status="completed")
        assert await mw.after(ctx, result) is result


class TestCheckpointMiddleware:
    """CheckpointMiddleware accumulates results."""

    async def test_accumulates_results(self):
        mw = CheckpointMiddleware()
        ctx = MiddlewareContext(sub_task=SubTask(id="st-1"), config=RuntimeConfig())
        result = AgentResult(status="completed", cost_usd=0.5)
        await mw.after(ctx, result)
        assert len(mw._results) == 1
        assert mw._results[0]["sub_task_id"] == "st-1"

    async def test_no_pool_no_error(self):
        mw = CheckpointMiddleware(pool=None)
        ctx = MiddlewareContext(sub_task=SubTask(id="st-1"), config=RuntimeConfig())
        result = AgentResult(status="completed", cost_usd=0.5)
        # Should not raise even without a pool
        returned = await mw.after(ctx, result)
        assert returned is result


class TestAlertMiddleware:
    """AlertMiddleware emits structlog alerts at thresholds."""

    async def test_no_alert_under_threshold(self):
        mw = AlertMiddleware(total_budget_usd=10.0)
        ctx = MiddlewareContext(sub_task=SubTask(), config=RuntimeConfig())
        result = AgentResult(status="completed", cost_usd=1.0)
        await mw.before(ctx)
        await mw.after(ctx, result)
        assert "budget_warn" not in mw._alerts_fired

    async def test_budget_warning_50pct(self):
        mw = AlertMiddleware(total_budget_usd=10.0)
        ctx = MiddlewareContext(sub_task=SubTask(), config=RuntimeConfig())
        await mw.before(ctx)
        # Spend 6.0 (60% > 50% threshold)
        result = AgentResult(status="completed", cost_usd=6.0)
        await mw.after(ctx, result)
        assert "budget_warn" in mw._alerts_fired

    async def test_budget_critical_80pct(self):
        mw = AlertMiddleware(total_budget_usd=10.0)
        ctx = MiddlewareContext(sub_task=SubTask(), config=RuntimeConfig())
        await mw.before(ctx)
        result = AgentResult(status="completed", cost_usd=9.0)
        await mw.after(ctx, result)
        assert "budget_critical" in mw._alerts_fired

    async def test_alert_fires_once(self):
        mw = AlertMiddleware(total_budget_usd=10.0)
        ctx = MiddlewareContext(sub_task=SubTask(), config=RuntimeConfig())
        await mw.before(ctx)
        # First call triggers warning
        r1 = AgentResult(status="completed", cost_usd=6.0)
        await mw.after(ctx, r1)
        alerts_after_first = len(mw._alerts_fired)
        # Second call should not add duplicate
        r2 = AgentResult(status="completed", cost_usd=0.1)
        await mw.after(ctx, r2)
        assert len(mw._alerts_fired) == alerts_after_first

    async def test_time_warning(self):
        thresholds = AlertThresholds(time_warn_seconds=0.001)
        mw = AlertMiddleware(total_budget_usd=10.0, thresholds=thresholds)
        ctx = MiddlewareContext(sub_task=SubTask(), config=RuntimeConfig())
        await mw.before(ctx)
        # Small delay to exceed threshold
        await asyncio.sleep(0.01)
        result = AgentResult(status="completed", cost_usd=0.1)
        await mw.after(ctx, result)
        assert "time_warn" in mw._alerts_fired
