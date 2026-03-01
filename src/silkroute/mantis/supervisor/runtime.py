"""SupervisorRuntime — meta-orchestrator for long-running compound workflows.

Implements the AgentRuntime Protocol by executing multi-step plans with:
- Sequential step execution respecting dependency order
- Inter-step context passing via plan.context[step_id]
- Retry with exponential backoff on failed steps
- Checkpoint persistence after each step (fire-and-forget)
- Conditional step execution via safe expression parsing
- Session create/resume/cancel lifecycle
"""

from __future__ import annotations

import asyncio
import json
from collections.abc import AsyncIterator, Callable
from datetime import UTC, datetime
from typing import TYPE_CHECKING, Any

import structlog

from silkroute.mantis.orchestrator.budget import BudgetExhaustedError, BudgetTracker
from silkroute.mantis.runtime.interface import AgentResult, AgentRuntime, RuntimeConfig
from silkroute.mantis.supervisor.models import (
    SessionStatus,
    StepStatus,
    SupervisorCheckpoint,
    SupervisorPlan,
    SupervisorSession,
    SupervisorStep,
)

if TYPE_CHECKING:
    import asyncpg

    from silkroute.config.settings import SupervisorConfig

log = structlog.get_logger()


class SupervisorRuntime:
    """Meta-orchestrator for long-running compound workflows.

    Implements AgentRuntime Protocol. Each step delegates to a child runtime
    (default: OrchestratorRuntime) via the registry. Steps communicate through
    plan.context[step_id] and are checkpointed after each completion.
    """

    def __init__(
        self,
        child_factory: Callable[[str | None], AgentRuntime] | None = None,
        supervisor_config: SupervisorConfig | None = None,
        db_pool: asyncpg.Pool | None = None,
    ) -> None:
        self._child_factory = child_factory or _default_child_factory
        self._config = supervisor_config
        self._db_pool = db_pool

    @property
    def name(self) -> str:
        return "supervisor"

    async def invoke(self, task: str, config: RuntimeConfig | None = None) -> AgentResult:
        """Build or load plan, execute steps, return aggregated result."""
        cfg = config or RuntimeConfig()

        plan = self._build_plan_from_task(task, cfg)

        session = SupervisorSession(
            project_id=cfg.project_id,
            plan=plan,
        )

        return await self._run_session(session, cfg)

    async def stream(self, task: str, config: RuntimeConfig | None = None) -> AsyncIterator[str]:
        """Yield step-level progress events as JSON."""
        cfg = config or RuntimeConfig()
        plan = self._build_plan_from_task(task, cfg)

        session = SupervisorSession(
            project_id=cfg.project_id,
            plan=plan,
        )

        session.status = SessionStatus.RUNNING

        tracker = BudgetTracker(total_usd=plan.total_budget_usd)

        yield json.dumps({
            "type": "supervisor_start",
            "session_id": session.id,
            "step_count": len(plan.steps),
        })

        while not plan.is_complete:
            step = plan.next_pending_step()
            if step is None:
                break

            if step.condition and not self._evaluate_condition(step.condition, plan.context):
                step.status = StepStatus.SKIPPED
                yield json.dumps({
                    "type": "step_skipped",
                    "step_id": step.id,
                    "reason": f"Condition not met: {step.condition}",
                })
                continue

            yield json.dumps({
                "type": "step_start",
                "step_id": step.id,
                "step_name": step.name,
            })

            try:
                await self._execute_step(step, session, tracker)
                yield json.dumps({
                    "type": "step_completed",
                    "step_id": step.id,
                    "status": step.status.value,
                    "cost_usd": step.cost_usd,
                    "output": step.output[:500],
                })
            except BudgetExhaustedError:
                yield json.dumps({
                    "type": "budget_exhausted",
                    "step_id": step.id,
                })
                break

        yield json.dumps({
            "type": "supervisor_complete",
            "session_id": session.id,
            "total_cost_usd": tracker.spent_usd,
            "status": plan.overall_status.value,
        })

    async def create_session(
        self,
        plan: SupervisorPlan,
        project_id: str = "default",
    ) -> SupervisorSession:
        """Create a persistent supervisor session."""
        session = SupervisorSession(
            project_id=project_id,
            plan=plan,
        )

        if self._db_pool is not None:
            from silkroute.db.repositories.supervisor import create_supervisor_session

            await create_supervisor_session(self._db_pool, session)

        return session

    async def resume_session(self, session_id: str) -> AgentResult:
        """Load checkpoint from DB and continue from last completed step."""
        if self._db_pool is None:
            return AgentResult(
                status="failed",
                error="Cannot resume: no database connection",
            )

        from silkroute.db.repositories.supervisor import get_supervisor_session

        session = await get_supervisor_session(self._db_pool, session_id)
        if session is None:
            return AgentResult(status="failed", error=f"Session {session_id} not found")

        if session.status == SessionStatus.COMPLETED:
            return AgentResult(
                status="completed",
                output="Session already completed",
                cost_usd=session.total_cost_usd,
            )

        if session.status == SessionStatus.CANCELLED:
            return AgentResult(
                status="failed",
                error="Session was cancelled",
            )

        # Restore context from checkpoint
        if session.checkpoint:
            session.plan.context = session.checkpoint.context_json

        return await self._run_session(session, RuntimeConfig(project_id=session.project_id))

    async def cancel_session(self, session_id: str) -> bool:
        """Set session status to CANCELLED."""
        if self._db_pool is None:
            return False

        from silkroute.db.repositories.supervisor import (
            get_supervisor_session,
            update_supervisor_session,
        )

        session = await get_supervisor_session(self._db_pool, session_id)
        if session is None:
            return False

        session.status = SessionStatus.CANCELLED
        await update_supervisor_session(self._db_pool, session)
        return True

    async def _run_session(
        self,
        session: SupervisorSession,
        config: RuntimeConfig,
    ) -> AgentResult:
        """Execute all pending steps in a session."""
        session.status = SessionStatus.RUNNING
        plan = session.plan

        step_timeout = self._config.step_timeout_seconds if self._config else 300
        checkpoint_enabled = self._config.checkpoint_enabled if self._config else True

        tracker = BudgetTracker(total_usd=plan.total_budget_usd)

        while not plan.is_complete:
            step = plan.next_pending_step()
            if step is None:
                break

            # Evaluate condition
            if step.condition and not self._evaluate_condition(step.condition, plan.context):
                step.status = StepStatus.SKIPPED
                log.info("supervisor_step_skipped", step_id=step.id, condition=step.condition)
                continue

            # Budget gate: check remaining before executing
            if tracker.remaining_usd <= 0:
                step.status = StepStatus.FAILED
                step.error = "Budget exhausted"
                log.warning("supervisor_budget_exhausted", step_id=step.id)
                break

            try:
                await asyncio.wait_for(
                    self._execute_step(step, session, tracker),
                    timeout=step_timeout,
                )
            except TimeoutError:
                step.status = StepStatus.FAILED
                step.error = f"Step timed out after {step_timeout}s"
                log.warning("supervisor_step_timeout", step_id=step.id)
            except BudgetExhaustedError as exc:
                step.status = StepStatus.FAILED
                step.error = str(exc)
                log.warning("supervisor_budget_exhausted", step_id=step.id)
                break

            # Checkpoint after each step
            if checkpoint_enabled:
                await self._checkpoint_session(session, tracker)

        # Determine final status
        session.status = plan.overall_status
        session.total_cost_usd = tracker.spent_usd

        if self._db_pool is not None:
            from silkroute.db.repositories.supervisor import update_supervisor_session

            await update_supervisor_session(self._db_pool, session)

        # Build aggregated output
        outputs = [s.output for s in plan.steps if s.output]
        merged = "\n\n---\n\n".join(outputs) if outputs else ""

        return AgentResult(
            status=session.status.value,
            session_id=session.id,
            iterations=sum(1 for s in plan.steps if s.status != StepStatus.PENDING),
            cost_usd=tracker.spent_usd,
            output=merged,
            error=session.error,
            metadata={
                "supervised": True,
                "step_count": len(plan.steps),
                "completed_steps": sum(1 for s in plan.steps if s.status == StepStatus.COMPLETED),
                "failed_steps": sum(1 for s in plan.steps if s.status == StepStatus.FAILED),
                "skipped_steps": sum(1 for s in plan.steps if s.status == StepStatus.SKIPPED),
            },
        )

    async def _execute_step(
        self,
        step: SupervisorStep,
        session: SupervisorSession,
        tracker: BudgetTracker,
    ) -> AgentResult:
        """Execute a single step with retry logic and context passing."""
        step.status = StepStatus.RUNNING
        step.started_at = datetime.now(UTC)

        max_retries = step.max_retries
        backoff = step.retry_backoff_seconds

        child = self._child_factory(step.runtime_type)
        child_cfg = RuntimeConfig(
            runtime_type=step.runtime_type,
            project_id=session.project_id,
            budget_limit_usd=tracker.remaining_usd,
            **(step.config or {}),
        )

        result = AgentResult(status="failed", error="not executed")
        for attempt in range(max_retries + 1):
            try:
                result = await child.invoke(step.description, child_cfg)
            except Exception as exc:
                log.error(
                    "supervisor_step_failed",
                    step_id=step.id,
                    attempt=attempt + 1,
                    error=str(exc),
                )
                result = AgentResult(status="failed", error=str(exc))

            if result.status in ("failed", "timeout") and attempt < max_retries:
                step.retry_count = attempt + 1
                delay = backoff * (2 ** attempt)
                log.info(
                    "supervisor_step_retry",
                    step_id=step.id,
                    attempt=attempt + 1,
                    delay=delay,
                )
                await asyncio.sleep(delay)
                continue
            break

        # Record result
        step.cost_usd = result.cost_usd
        step.output = result.output
        step.error = result.error
        step.completed_at = datetime.now(UTC)

        if result.success:
            step.status = StepStatus.COMPLETED
            await tracker.record_spend(result.cost_usd)
            # Store output in plan context for downstream steps
            session.plan.context[step.id] = {
                "status": "completed",
                "output": result.output,
                "cost_usd": result.cost_usd,
            }
        elif step.skip_on_failure:
            step.status = StepStatus.SKIPPED
            session.plan.context[step.id] = {
                "status": "skipped",
                "error": result.error,
            }
        else:
            step.status = StepStatus.FAILED
            session.plan.context[step.id] = {
                "status": "failed",
                "error": result.error,
            }

        log.info(
            "supervisor_step_completed",
            step_id=step.id,
            status=step.status.value,
            cost_usd=step.cost_usd,
            retries=step.retry_count,
        )

        return result

    def _evaluate_condition(self, condition: str, context: dict[str, Any]) -> bool:
        """Evaluate a step condition against the plan context.

        Supports simple structured expressions (NOT arbitrary code):
        - "step_id.status == completed" — check step status
        - "step_id.output contains keyword" — substring check
        - "step_id" — key existence check
        """
        condition = condition.strip()

        # Pattern: "step_id.field == value"
        if "==" in condition:
            parts = condition.split("==", 1)
            if len(parts) == 2:
                key_path = parts[0].strip()
                expected = parts[1].strip()
                return self._resolve_path(key_path, context) == expected
            return False

        # Pattern: "step_id.field contains value"
        if " contains " in condition:
            parts = condition.split(" contains ", 1)
            if len(parts) == 2:
                key_path = parts[0].strip()
                substring = parts[1].strip()
                resolved = self._resolve_path(key_path, context)
                return isinstance(resolved, str) and substring in resolved
            return False

        # Pattern: "step_id" — simple key existence
        return condition in context

    @staticmethod
    def _resolve_path(key_path: str, context: dict[str, Any]) -> object:
        """Resolve a dotted path like 'step1.status' against context."""
        parts = key_path.split(".", 1)
        if len(parts) == 1:
            return context.get(parts[0])
        step_id, field = parts
        step_data = context.get(step_id)
        if isinstance(step_data, dict):
            return step_data.get(field)
        return None

    async def _checkpoint_session(
        self,
        session: SupervisorSession,
        tracker: BudgetTracker,
    ) -> None:
        """Fire-and-forget DB checkpoint write."""
        if self._db_pool is None:
            return

        checkpoint = SupervisorCheckpoint(
            session_id=session.id,
            plan_json=session.plan.to_dict(),
            context_json=session.plan.context,
            step_results={
                s.id: {"status": s.status.value, "cost_usd": s.cost_usd}
                for s in session.plan.steps
                if s.status != StepStatus.PENDING
            },
            total_cost_usd=tracker.spent_usd,
        )
        session.checkpoint = checkpoint

        try:
            from silkroute.db.repositories.supervisor import update_checkpoint

            await update_checkpoint(
                self._db_pool, session.id, checkpoint, tracker.spent_usd
            )
        except Exception:
            log.debug("supervisor_checkpoint_failed", session_id=session.id)

    def _build_plan_from_task(
        self,
        task: str,
        config: RuntimeConfig,
    ) -> SupervisorPlan:
        """Parse a task description into a supervisor plan.

        Uses simple keyword splitting (like KeywordDecomposer) to create
        sequential steps. For compound tasks, splits on "and then" / "then".
        """
        steps: list[SupervisorStep] = []

        # Check for numbered list pattern: "1. task 2. task"
        import re

        numbered = re.split(r"\d+\.\s+", task)
        numbered = [s.strip() for s in numbered if s.strip()]

        if len(numbered) > 1:
            prev_id: str | None = None
            for i, desc in enumerate(numbered):
                step = SupervisorStep(
                    name=f"step_{i + 1}",
                    description=desc,
                    depends_on=[prev_id] if prev_id else [],
                )
                steps.append(step)
                prev_id = step.id
        elif " and then " in task or " then " in task:
            parts = re.split(r"\s+(?:and\s+)?then\s+", task)
            parts = [p.strip() for p in parts if p.strip()]
            prev_id = None
            for i, desc in enumerate(parts):
                step = SupervisorStep(
                    name=f"step_{i + 1}",
                    description=desc,
                    depends_on=[prev_id] if prev_id else [],
                )
                steps.append(step)
                prev_id = step.id
        else:
            steps.append(SupervisorStep(
                name="step_1",
                description=task,
            ))

        return SupervisorPlan(
            project_id=config.project_id,
            description=task,
            steps=steps,
            total_budget_usd=config.budget_limit_usd,
        )


def _default_child_factory(runtime_type: str | None = None) -> AgentRuntime:
    """Default factory — delegates to the runtime registry."""
    from silkroute.mantis.runtime.registry import get_runtime

    return get_runtime(runtime_type)
