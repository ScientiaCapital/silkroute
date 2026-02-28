"""Middleware chain for sub-agent execution.

Each middleware wraps a sub-task execution with before/after hooks.
The chain runs in order: validation → budget → logging.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Protocol

import structlog

from silkroute.mantis.orchestrator.budget import BudgetExhaustedError, BudgetTracker
from silkroute.mantis.orchestrator.models import SubTask
from silkroute.mantis.runtime.interface import AgentResult, RuntimeConfig

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
    """Enforces budget constraints on sub-tasks."""

    def __init__(self, tracker: BudgetTracker) -> None:
        self._tracker = tracker

    async def before(self, ctx: MiddlewareContext) -> MiddlewareContext:
        remaining = self._tracker.remaining_usd
        if remaining <= 0:
            raise BudgetExhaustedError(
                f"Budget exhausted: ${self._tracker.spent_usd:.4f} / "
                f"${self._tracker.total_usd:.4f}"
            )

        # Cap sub-task budget to remaining
        ctx.sub_task.budget_usd = min(ctx.sub_task.budget_usd, remaining)
        ctx.budget_remaining_usd = remaining
        return ctx

    async def after(self, ctx: MiddlewareContext, result: AgentResult) -> AgentResult:
        await self._tracker.record_spend(result.cost_usd)
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
