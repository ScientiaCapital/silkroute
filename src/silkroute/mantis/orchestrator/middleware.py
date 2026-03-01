"""Middleware chain for sub-agent execution.

Each middleware wraps a sub-task execution with before/after hooks.
The chain runs in order: validation → budget → logging.

Additional middleware (Phase 4):
- RetryMiddleware: injects retry config into ctx.metadata
- CheckpointMiddleware: fire-and-forget DB persistence after each sub-task
- AlertMiddleware: structlog alerts at budget/time thresholds
"""

from __future__ import annotations

import asyncio
import time
from dataclasses import dataclass, field
from typing import TYPE_CHECKING, Any, Protocol

import structlog

from silkroute.mantis.orchestrator.budget import BudgetExhaustedError, BudgetTracker
from silkroute.mantis.orchestrator.models import SubTask
from silkroute.mantis.runtime.interface import AgentResult, RuntimeConfig

if TYPE_CHECKING:
    import asyncpg

log = structlog.get_logger()


@dataclass
class MiddlewareContext:
    """Context passed through the middleware chain."""

    sub_task: SubTask
    config: RuntimeConfig
    budget_remaining_usd: float = 0.0
    parent_task: str = ""
    stage: int = 0
    metadata: dict[str, Any] = field(default_factory=dict)


class Middleware(Protocol):
    """Protocol for sub-agent middleware."""

    async def before(self, ctx: MiddlewareContext) -> MiddlewareContext:
        """Pre-execution hook. May modify context or raise to abort."""
        ...

    async def after(self, ctx: MiddlewareContext, result: AgentResult) -> AgentResult:
        """Post-execution hook. May modify result."""
        ...


class ValidationMiddleware:
    """Validates sub-task configuration before execution."""

    async def before(self, ctx: MiddlewareContext) -> MiddlewareContext:
        st = ctx.sub_task
        if st.max_iterations < 1:
            raise ValueError(f"Sub-task {st.id}: max_iterations must be >= 1")
        if st.budget_usd <= 0:
            raise ValueError(f"Sub-task {st.id}: budget_usd must be > 0")
        return ctx

    async def after(self, ctx: MiddlewareContext, result: AgentResult) -> AgentResult:
        return result


class BudgetMiddleware:
    """Enforces budget constraints via atomic reserve-then-settle.

    before(): Atomically reserves the sub-task's budget via try_reserve().
    after(): Settles the actual spend, releasing over-reservation.
    """

    def __init__(self, tracker: BudgetTracker) -> None:
        self._tracker = tracker

    async def before(self, ctx: MiddlewareContext) -> MiddlewareContext:
        reserved = await self._tracker.try_reserve(ctx.sub_task.budget_usd)
        if not reserved:
            raise BudgetExhaustedError(
                f"Budget exhausted: ${self._tracker.spent_usd:.4f} / "
                f"${self._tracker.total_usd:.4f}"
            )
        ctx.budget_remaining_usd = self._tracker.remaining_usd
        return ctx

    async def after(self, ctx: MiddlewareContext, result: AgentResult) -> AgentResult:
        await self._tracker.settle(ctx.sub_task.budget_usd, result.cost_usd)
        return result


class LoggingMiddleware:
    """Logs sub-agent lifecycle events via structlog."""

    async def before(self, ctx: MiddlewareContext) -> MiddlewareContext:
        log.info(
            "sub_agent_starting",
            sub_task_id=ctx.sub_task.id,
            stage=ctx.stage,
            runtime=ctx.sub_task.runtime_type,
            budget_usd=ctx.sub_task.budget_usd,
        )
        return ctx

    async def after(self, ctx: MiddlewareContext, result: AgentResult) -> AgentResult:
        log.info(
            "sub_agent_completed",
            sub_task_id=ctx.sub_task.id,
            status=result.status,
            cost_usd=result.cost_usd,
            iterations=result.iterations,
        )
        return result


# ──────────────────────────────────────────────────────────────
# Phase 4 middleware
# ──────────────────────────────────────────────────────────────


@dataclass
class RetryConfig:
    """Configuration for retry behavior."""

    max_retries: int = 3
    backoff_base: float = 1.0
    backoff_factor: float = 2.0
    retryable_statuses: frozenset[str] = field(
        default_factory=lambda: frozenset({"failed", "timeout"})
    )


class RetryMiddleware:
    """Injects retry configuration into middleware context.

    The actual retry loop lives in _execute_sub_task() — this middleware
    only provides the config. Keeps the Middleware Protocol clean.
    """

    def __init__(self, config: RetryConfig | None = None) -> None:
        self._config = config or RetryConfig()

    async def before(self, ctx: MiddlewareContext) -> MiddlewareContext:
        ctx.metadata["retry_config"] = self._config
        return ctx

    async def after(self, ctx: MiddlewareContext, result: AgentResult) -> AgentResult:
        return result


class CheckpointMiddleware:
    """Fire-and-forget DB persistence after each sub-task.

    If no pool is provided, silently skips (fail-open for persistence).
    """

    def __init__(self, pool: asyncpg.Pool | None = None, session_id: str = "") -> None:
        self._pool = pool
        self._session_id = session_id
        self._results: list[dict[str, Any]] = []

    async def before(self, ctx: MiddlewareContext) -> MiddlewareContext:
        return ctx

    async def after(self, ctx: MiddlewareContext, result: AgentResult) -> AgentResult:
        self._results.append({
            "sub_task_id": ctx.sub_task.id,
            "status": result.status,
            "cost_usd": result.cost_usd,
        })
        if self._pool is not None:
            asyncio.create_task(self._persist(ctx, result))
        return result

    async def _persist(self, ctx: MiddlewareContext, result: AgentResult) -> None:
        """Write checkpoint data to DB. Swallows errors (fail-open)."""
        try:
            await self._pool.execute(  # type: ignore[union-attr]
                """
                UPDATE supervisor_sessions
                SET checkpoint_json = checkpoint_json || $2::jsonb,
                    updated_at = NOW()
                WHERE id = $1
                """,
                self._session_id,
                f'{{"last_sub_task": "{ctx.sub_task.id}", "status": "{result.status}"}}',
            )
        except Exception:
            log.debug(
                "checkpoint_persist_failed",
                session_id=self._session_id,
                sub_task_id=ctx.sub_task.id,
            )


@dataclass
class AlertThresholds:
    """Threshold configuration for alert middleware."""

    budget_warn_pct: float = 0.50
    budget_critical_pct: float = 0.80
    time_warn_seconds: float = 60.0


class AlertMiddleware:
    """Emits structlog alerts when budget or time thresholds are crossed.

    Each threshold fires once (tracked in _alerts_fired set).
    """

    def __init__(
        self,
        total_budget_usd: float,
        thresholds: AlertThresholds | None = None,
    ) -> None:
        self._total_budget = total_budget_usd
        self._thresholds = thresholds or AlertThresholds()
        self._cumulative_cost: float = 0.0
        self._start_time: float = 0.0
        self._alerts_fired: set[str] = set()

    async def before(self, ctx: MiddlewareContext) -> MiddlewareContext:
        if self._start_time == 0.0:
            self._start_time = time.monotonic()
        return ctx

    async def after(self, ctx: MiddlewareContext, result: AgentResult) -> AgentResult:
        self._cumulative_cost += result.cost_usd

        # Budget alerts
        if self._total_budget > 0:
            pct = self._cumulative_cost / self._total_budget
            is_critical = pct >= self._thresholds.budget_critical_pct
            if is_critical and "budget_critical" not in self._alerts_fired:
                self._alerts_fired.add("budget_critical")
                log.warning(
                    "alert_budget_critical",
                    spent_usd=self._cumulative_cost,
                    total_usd=self._total_budget,
                    pct=round(pct * 100, 1),
                )
            elif pct >= self._thresholds.budget_warn_pct and "budget_warn" not in self._alerts_fired:  # noqa: E501
                self._alerts_fired.add("budget_warn")
                log.warning(
                    "alert_budget_warning",
                    spent_usd=self._cumulative_cost,
                    total_usd=self._total_budget,
                    pct=round(pct * 100, 1),
                )

        # Time alerts
        elapsed = time.monotonic() - self._start_time
        if elapsed >= self._thresholds.time_warn_seconds and "time_warn" not in self._alerts_fired:
            self._alerts_fired.add("time_warn")
            log.warning(
                "alert_time_warning",
                elapsed_seconds=round(elapsed, 1),
                threshold_seconds=self._thresholds.time_warn_seconds,
            )

        return result
