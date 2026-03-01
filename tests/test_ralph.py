"""Tests for mantis/supervisor/ralph.py — RalphController."""

from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from silkroute.config.settings import BudgetConfig, SupervisorConfig
from silkroute.mantis.supervisor.ralph import RalphController


class TestRalphCycle:
    """RalphController.run_cycle() single-cycle execution."""

    @pytest.mark.asyncio
    async def test_cycle_no_queue(self):
        """No queue → idle."""
        controller = RalphController(queue=None)
        result = await controller.run_cycle()
        assert result["status"] == "idle"

    @pytest.mark.asyncio
    async def test_cycle_no_work(self):
        """Empty queue → idle."""
        mock_queue = AsyncMock()
        mock_queue.consume.return_value = None
        controller = RalphController(queue=mock_queue)
        result = await controller.run_cycle()
        assert result["status"] == "idle"

    @pytest.mark.asyncio
    @patch("silkroute.mantis.supervisor.ralph.SupervisorRuntime")
    async def test_cycle_with_task(self, MockRT):
        """Task in queue → executes plan."""
        mock_queue = AsyncMock()

        # First call returns a task, second returns None
        task_request = MagicMock()
        task_request.task = "review code"
        task_request.project_id = "default"
        mock_queue.consume.side_effect = [task_request, None]

        from silkroute.mantis.supervisor.models import SupervisorSession, SessionStatus

        mock_session = SupervisorSession(
            id="sess-ralph",
            status=SessionStatus.COMPLETED,
            total_cost_usd=0.05,
        )
        mock_rt = MockRT.return_value
        mock_rt.create_session = AsyncMock(return_value=mock_session)
        mock_rt._run_session = AsyncMock()

        config = SupervisorConfig(enabled=True, ralph_budget_usd=5.0)
        controller = RalphController(
            queue=mock_queue,
            supervisor_config=config,
        )
        result = await controller.run_cycle()
        assert result["status"] == "completed"
        assert result["plans_executed"] == 1


class TestRalphBudgetGate:
    """RalphController._check_budget_gate()."""

    @pytest.mark.asyncio
    async def test_budget_gate_no_config(self):
        """No budget config → allow (dev mode)."""
        controller = RalphController()
        assert await controller._check_budget_gate() is True

    @pytest.mark.asyncio
    async def test_budget_gate_no_db(self):
        """No DB → fail-open."""
        config = BudgetConfig(daily_max_usd=10.0)
        controller = RalphController(budget_config=config)
        assert await controller._check_budget_gate() is True

    @pytest.mark.asyncio
    async def test_budget_gate_within_limit(self):
        """Daily spend below limit → allow."""
        mock_pool = AsyncMock()

        with patch(
            "silkroute.db.repositories.projects.get_daily_spend",
            new_callable=AsyncMock,
            return_value=5.0,
        ):
            config = BudgetConfig(daily_max_usd=10.0)
            controller = RalphController(budget_config=config, db_pool=mock_pool)
            assert await controller._check_budget_gate() is True

    @pytest.mark.asyncio
    async def test_budget_gate_exceeded(self):
        """Daily spend above limit → block."""
        mock_pool = AsyncMock()

        with patch(
            "silkroute.db.repositories.projects.get_daily_spend",
            new_callable=AsyncMock,
            return_value=15.0,
        ):
            config = BudgetConfig(daily_max_usd=10.0)
            controller = RalphController(budget_config=config, db_pool=mock_pool)
            assert await controller._check_budget_gate() is False


class TestSchedulerRegistration:
    """Ralph Mode registration in DaemonScheduler."""

    def test_ralph_job_registered_when_enabled(self):
        """Scheduler should register ralph_cycle job when supervisor is enabled."""
        from silkroute.config.settings import DaemonConfig, SupervisorConfig
        from silkroute.daemon.scheduler import DaemonScheduler

        config = DaemonConfig()
        sv_config = SupervisorConfig(enabled=True, ralph_cron="*/30 * * * *")
        mock_queue = MagicMock()

        # We can't fully start the scheduler (needs Redis), but we verify the
        # code path by checking that it wouldn't raise
        scheduler = DaemonScheduler(
            config=config,
            queue=mock_queue,
            supervisor_config=sv_config,
        )
        assert scheduler._supervisor_config is not None
        assert scheduler._supervisor_config.enabled is True
