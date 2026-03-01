"""Ralph Mode — autonomous supervisor scheduling loop.

Runs as a DaemonScheduler cron job. Each cycle:
1. Checks global budget gate
2. Discovers pending work from the task queue
3. Creates a SupervisorPlan
4. Executes via SupervisorRuntime
5. Records results, handles failures
"""

from __future__ import annotations

from typing import TYPE_CHECKING

import structlog

from silkroute.mantis.runtime.interface import RuntimeConfig
from silkroute.mantis.supervisor.models import (
    SessionStatus,
    SupervisorPlan,
    SupervisorSession,
    SupervisorStep,
)
from silkroute.mantis.supervisor.runtime import SupervisorRuntime

if TYPE_CHECKING:
    import asyncpg

    from silkroute.config.settings import BudgetConfig, SupervisorConfig
    from silkroute.daemon.queue import TaskQueue

log = structlog.get_logger()


class RalphController:
    """Autonomous supervisor loop — runs via DaemonScheduler cron.

    Each cycle checks budget, discovers queued tasks, builds a
    SupervisorPlan, and executes via SupervisorRuntime.
    """

    def __init__(
        self,
        queue: TaskQueue | None = None,
        supervisor_config: SupervisorConfig | None = None,
        budget_config: BudgetConfig | None = None,
        db_pool: asyncpg.Pool | None = None,
    ) -> None:
        self._queue = queue
        self._supervisor_config = supervisor_config
        self._budget_config = budget_config
        self._db_pool = db_pool

    async def run_cycle(self) -> dict:
        """Execute one autonomous Ralph cycle.

        Returns a summary dict with cycle results.
        """
        log.info("ralph_cycle_start")

        # 1. Budget gate
        if not await self._check_budget_gate():
            log.warning("ralph_budget_gate_blocked")
            return {"status": "blocked", "reason": "budget_exceeded"}

        # 2. Discover work
        plans = await self._discover_work()
        if not plans:
            log.info("ralph_no_work")
            return {"status": "idle", "reason": "no_pending_work"}

        # 3. Execute each plan
        results = []
        for plan in plans:
            try:
                session = await self._execute_plan(plan)
                results.append({
                    "session_id": session.id,
                    "status": session.status.value,
                    "cost_usd": session.total_cost_usd,
                })
            except (RuntimeError, OSError, ValueError, TimeoutError) as exc:
                await self._handle_failure(None, exc)
                results.append({
                    "status": "failed",
                    "error": str(exc),
                })

        log.info("ralph_cycle_complete", plans_executed=len(results))
        return {
            "status": "completed",
            "plans_executed": len(results),
            "results": results,
        }

    async def _check_budget_gate(self) -> bool:
        """Check global budget before proceeding.

        Returns True if budget is available, False otherwise.
        """
        if self._budget_config is None:
            return True  # No config = dev mode, allow

        if self._db_pool is None:
            return True  # No DB = fail-open

        try:
            from silkroute.db.repositories.projects import get_daily_spend

            daily_spend = await get_daily_spend(self._db_pool, "default")
            return daily_spend < self._budget_config.daily_max_usd
        except (RuntimeError, OSError, ValueError) as exc:
            log.debug("ralph_budget_check_failed", error=str(exc))
            return True  # Fail-open

    async def _discover_work(self) -> list[SupervisorPlan]:
        """Discover pending work from the task queue."""
        if self._queue is None:
            return []

        # Consume up to 3 tasks per cycle
        plans = []
        for _ in range(3):
            task_request = await self._queue.consume(timeout=1.0)
            if task_request is None:
                break

            budget = self._supervisor_config.ralph_budget_usd if self._supervisor_config else 5.0
            plan = SupervisorPlan(
                project_id=task_request.project_id,
                description=task_request.task,
                steps=[
                    SupervisorStep(
                        name="auto_task",
                        description=task_request.task,
                    ),
                ],
                total_budget_usd=budget,
            )
            plans.append(plan)

        return plans

    async def _execute_plan(self, plan: SupervisorPlan) -> SupervisorSession:
        """Execute a plan via SupervisorRuntime."""
        rt = SupervisorRuntime(
            supervisor_config=self._supervisor_config,
            db_pool=self._db_pool,
        )

        session = await rt.create_session(plan, project_id=plan.project_id)

        budget = self._supervisor_config.ralph_budget_usd if self._supervisor_config else 5.0
        await rt._run_session(session, RuntimeConfig(
            project_id=plan.project_id,
            budget_limit_usd=budget,
        ))

        return session

    async def _handle_failure(
        self,
        session: SupervisorSession | None,
        error: Exception,
    ) -> None:
        """Handle cycle failure — log and record."""
        log.error(
            "ralph_cycle_failure",
            session_id=session.id if session else None,
            error=str(error),
        )

        if session is not None and self._db_pool is not None:
            from silkroute.db.repositories.supervisor import update_supervisor_session

            session.status = SessionStatus.FAILED
            session.error = str(error)
            try:
                await update_supervisor_session(self._db_pool, session)
            except (OSError, RuntimeError, ValueError):
                log.debug("ralph_failure_persist_failed")
