"""OrchestratorRuntime — multi-agent task orchestration.

Implements the AgentRuntime Protocol by decomposing tasks into sub-tasks,
delegating each to a child runtime, and aggregating results. Sub-tasks
are executed in topologically-sorted stages: parallel within stages,
sequential between stages.
"""

from __future__ import annotations

import asyncio
import time
from collections.abc import AsyncIterator, Callable
from typing import Any

import structlog

from silkroute.mantis.orchestrator.aggregator import aggregate_results
from silkroute.mantis.orchestrator.budget import (
    BudgetExhaustedError,
    BudgetTracker,
    allocate_budget,
)
from silkroute.mantis.orchestrator.decomposer import KeywordDecomposer, TaskDecomposer
from silkroute.mantis.orchestrator.middleware import (
    BudgetMiddleware,
    LoggingMiddleware,
    MiddlewareContext,
    RetryConfig,
    ValidationMiddleware,
)
from silkroute.mantis.orchestrator.models import (
    SubAgentResult,
    SubTask,
)
from silkroute.mantis.runtime.interface import AgentResult, AgentRuntime, RuntimeConfig

log = structlog.get_logger()


class OrchestratorRuntime:
    """Multi-agent orchestrator implementing the AgentRuntime Protocol.

    Decomposes tasks into sub-tasks via a TaskDecomposer, allocates budget,
    runs sub-tasks through a middleware chain, and aggregates results.

    Args:
        decomposer: Strategy for splitting tasks (default: KeywordDecomposer).
        child_factory: Factory for creating child runtimes (default: get_runtime).
        max_sub_tasks: Maximum sub-tasks per orchestration.
        stage_timeout_seconds: Timeout per execution stage.
    """

    def __init__(
        self,
        decomposer: TaskDecomposer | None = None,
        child_factory: Callable[[str | None], AgentRuntime] | None = None,
        max_sub_tasks: int = 5,
        stage_timeout_seconds: int = 120,
    ) -> None:
        self._decomposer: TaskDecomposer = decomposer or KeywordDecomposer()
        self._child_factory = child_factory or _default_child_factory
        self._max_sub_tasks = max_sub_tasks
        self._stage_timeout = stage_timeout_seconds

    @property
    def name(self) -> str:
        return "orchestrator"

    async def invoke(self, task: str, config: RuntimeConfig | None = None) -> AgentResult:
        """Decompose task, execute sub-tasks, and return aggregated result."""
        cfg = config or RuntimeConfig()

        # 1. Decompose
        plan = self._decomposer.decompose(task, cfg)

        # Cap sub-tasks
        if len(plan.sub_tasks) > self._max_sub_tasks:
            plan.sub_tasks = plan.sub_tasks[: self._max_sub_tasks]

        # 2. Allocate budget
        plan.total_budget_usd = cfg.budget_limit_usd
        plan = allocate_budget(plan)

        # 3. Set up budget tracker and middleware chain
        tracker = BudgetTracker(total_usd=cfg.budget_limit_usd)
        middleware = [
            ValidationMiddleware(),
            BudgetMiddleware(tracker),
            LoggingMiddleware(),
        ]

        # 4. Execute stages
        stages = plan.stages
        all_results: list[SubAgentResult] = []

        for stage_idx, stage in enumerate(stages):
            try:
                stage_results = await asyncio.wait_for(
                    self._execute_stage(stage, stage_idx, cfg, middleware, tracker),
                    timeout=self._stage_timeout,
                )
                all_results.extend(stage_results)
            except TimeoutError:
                log.warning(
                    "orchestrator_stage_timeout",
                    stage=stage_idx,
                    timeout=self._stage_timeout,
                )
                for st in stage:
                    all_results.append(
                        SubAgentResult(
                            sub_task_id=st.id,
                            agent_result=AgentResult(
                                status="timeout",
                                error=f"Stage {stage_idx} timed out",
                            ),
                            stage=stage_idx,
                        )
                    )
                break
            except BudgetExhaustedError:
                log.warning("orchestrator_budget_exhausted", stage=stage_idx)
                break

        # 5. Aggregate
        orch_result = aggregate_results(all_results, plan, tracker)

        return AgentResult(
            status=orch_result.status,
            output=orch_result.merged_output,
            iterations=orch_result.total_iterations,
            cost_usd=orch_result.total_cost_usd,
            error="" if orch_result.status == "completed" else orch_result.status,
            metadata={
                "orchestrated": True,
                "sub_task_count": len(plan.sub_tasks),
                "stage_count": len(stages),
                "sub_results": [
                    {
                        "sub_task_id": sr.sub_task_id,
                        "status": sr.agent_result.status,
                        "cost_usd": sr.agent_result.cost_usd,
                    }
                    for sr in all_results
                ],
            },
        )

    async def stream(self, task: str, config: RuntimeConfig | None = None) -> AsyncIterator[str]:
        """Stream per-stage markers and sub-task outputs."""
        import json

        cfg = config or RuntimeConfig()
        plan = self._decomposer.decompose(task, cfg)

        if len(plan.sub_tasks) > self._max_sub_tasks:
            plan.sub_tasks = plan.sub_tasks[: self._max_sub_tasks]

        plan.total_budget_usd = cfg.budget_limit_usd
        plan = allocate_budget(plan)
        tracker = BudgetTracker(total_usd=cfg.budget_limit_usd)

        stages = plan.stages
        for stage_idx, stage in enumerate(stages):
            yield json.dumps({
                "type": "stage_start",
                "stage": stage_idx,
                "sub_tasks": [st.id for st in stage],
            })

            # R2: Execute sub-tasks within a stage in parallel
            async def _run_sub_task(st: SubTask) -> dict[str, Any]:
                child = self._child_factory(st.runtime_type)
                child_cfg = RuntimeConfig(
                    runtime_type=st.runtime_type,
                    max_iterations=st.max_iterations,
                    budget_limit_usd=st.budget_usd,
                )
                try:
                    result = await child.invoke(st.description, child_cfg)
                    await tracker.record_spend(result.cost_usd)
                    return {
                        "type": "sub_task_completed",
                        "sub_task_id": st.id,
                        "status": result.status,
                        "output": result.output[:500],
                    }
                except (
                    asyncio.TimeoutError,
                    BudgetExhaustedError,
                    RuntimeError,
                    OSError,
                    ValueError,
                ) as exc:
                    return {
                        "type": "sub_task_error",
                        "sub_task_id": st.id,
                        "error": str(exc),
                    }

            results = await asyncio.gather(*[_run_sub_task(st) for st in stage])
            for event in results:
                yield json.dumps(event)

    async def _execute_stage(
        self,
        stage: list[SubTask],
        stage_idx: int,
        config: RuntimeConfig,
        middleware: list[Any],
        tracker: BudgetTracker,
    ) -> list[SubAgentResult]:
        """Execute all sub-tasks in a stage concurrently."""
        tasks = [
            self._execute_sub_task(st, stage_idx, config, middleware, tracker)
            for st in stage
        ]
        return list(await asyncio.gather(*tasks))

    async def _execute_sub_task(
        self,
        sub_task: SubTask,
        stage_idx: int,
        config: RuntimeConfig,
        middleware: list[Any],
        tracker: BudgetTracker,
    ) -> SubAgentResult:
        """Execute a single sub-task with middleware chain."""
        start_ms = int(time.monotonic() * 1000)

        ctx = MiddlewareContext(
            sub_task=sub_task,
            config=config,
            parent_task=sub_task.parent_task,
            stage=stage_idx,
        )

        # Run before middleware
        try:
            for mw in middleware:
                ctx = await mw.before(ctx)
        except (ValueError, BudgetExhaustedError) as exc:
            return SubAgentResult(
                sub_task_id=sub_task.id,
                agent_result=AgentResult(
                    status="failed",
                    error=str(exc),
                ),
                runtime_used=sub_task.runtime_type,
                stage=stage_idx,
                elapsed_ms=int(time.monotonic() * 1000) - start_ms,
            )

        # Execute via child runtime with optional retry
        child = self._child_factory(sub_task.runtime_type)
        child_cfg = RuntimeConfig(
            runtime_type=sub_task.runtime_type,
            max_iterations=sub_task.max_iterations,
            budget_limit_usd=sub_task.budget_usd,
        )

        retry_config: RetryConfig | None = ctx.metadata.get("retry_config")
        max_attempts = (retry_config.max_retries + 1) if retry_config else 1

        result = AgentResult(status="failed", error="not executed")
        for attempt in range(max_attempts):
            try:
                result = await child.invoke(sub_task.description, child_cfg)
            except Exception as exc:
                log.error(
                    "sub_task_execution_failed",
                    sub_task_id=sub_task.id,
                    error=str(exc),
                    attempt=attempt + 1,
                )
                result = AgentResult(status="failed", error=str(exc))

            if (
                retry_config
                and attempt < max_attempts - 1
                and result.status in retry_config.retryable_statuses
            ):
                delay = retry_config.backoff_base * (retry_config.backoff_factor ** attempt)
                log.info(
                    "sub_task_retry",
                    sub_task_id=sub_task.id,
                    attempt=attempt + 1,
                    delay=delay,
                )
                await asyncio.sleep(delay)
                continue
            break

        # Run after middleware
        for mw in reversed(middleware):
            result = await mw.after(ctx, result)

        elapsed = int(time.monotonic() * 1000) - start_ms
        return SubAgentResult(
            sub_task_id=sub_task.id,
            agent_result=result,
            runtime_used=sub_task.runtime_type,
            stage=stage_idx,
            elapsed_ms=elapsed,
        )


def _default_child_factory(runtime_type: str | None = None) -> AgentRuntime:
    """Default factory — delegates to the runtime registry."""
    from silkroute.mantis.runtime.registry import get_runtime

    return get_runtime(runtime_type)
