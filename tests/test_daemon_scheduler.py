"""Tests for daemon scheduler — APScheduler registration, job submission."""

from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from silkroute.daemon.queue import TaskQueue
from silkroute.daemon.scheduler import DaemonScheduler


def _make_daemon_config(
    *,
    nightly_scan_enabled: bool = True,
    nightly_scan_cron: str = "0 3 * * *",
    dependency_check_cron: str = "0 6 * * 1",
) -> MagicMock:
    """Create a mock DaemonConfig for testing."""
    config = MagicMock()
    config.nightly_scan_enabled = nightly_scan_enabled
    config.nightly_scan_cron = nightly_scan_cron
    config.dependency_check_cron = dependency_check_cron
    return config


class TestDaemonScheduler:
    """DaemonScheduler unit tests."""

    def test_init(self) -> None:
        config = _make_daemon_config()
        queue = MagicMock(spec=TaskQueue)
        scheduler = DaemonScheduler(config, queue)
        assert scheduler._scheduler is None

    @patch("silkroute.daemon.scheduler.AsyncIOScheduler")
    @patch("silkroute.daemon.scheduler.RedisJobStore")
    def test_start_creates_scheduler_with_redis_jobstore(
        self, mock_jobstore_cls: MagicMock, mock_scheduler_cls: MagicMock
    ) -> None:
        config = _make_daemon_config()
        queue = MagicMock(spec=TaskQueue)
        scheduler = DaemonScheduler(config, queue)

        mock_scheduler_instance = MagicMock()
        mock_scheduler_instance.get_jobs.return_value = []
        mock_scheduler_cls.return_value = mock_scheduler_instance

        scheduler.start()

        mock_jobstore_cls.assert_called_once()
        mock_scheduler_cls.assert_called_once()
        mock_scheduler_instance.start.assert_called_once()

    @patch("silkroute.daemon.scheduler.AsyncIOScheduler")
    @patch("silkroute.daemon.scheduler.RedisJobStore")
    def test_start_registers_nightly_scan(
        self, mock_jobstore_cls: MagicMock, mock_scheduler_cls: MagicMock
    ) -> None:
        config = _make_daemon_config(nightly_scan_enabled=True)
        queue = MagicMock(spec=TaskQueue)
        scheduler = DaemonScheduler(config, queue)

        mock_scheduler_instance = MagicMock()
        mock_scheduler_instance.get_jobs.return_value = [MagicMock(), MagicMock()]
        mock_scheduler_cls.return_value = mock_scheduler_instance

        scheduler.start()

        # Should have 2 add_job calls: nightly_scan + dependency_check
        assert mock_scheduler_instance.add_job.call_count == 2
        job_ids = [
            call.kwargs.get("id") or call[1].get("id", "")
            for call in mock_scheduler_instance.add_job.call_args_list
        ]
        assert "nightly_scan" in job_ids
        assert "dependency_check" in job_ids

    @patch("silkroute.daemon.scheduler.AsyncIOScheduler")
    @patch("silkroute.daemon.scheduler.RedisJobStore")
    def test_start_skips_nightly_scan_when_disabled(
        self, mock_jobstore_cls: MagicMock, mock_scheduler_cls: MagicMock
    ) -> None:
        config = _make_daemon_config(nightly_scan_enabled=False)
        queue = MagicMock(spec=TaskQueue)
        scheduler = DaemonScheduler(config, queue)

        mock_scheduler_instance = MagicMock()
        mock_scheduler_instance.get_jobs.return_value = [MagicMock()]
        mock_scheduler_cls.return_value = mock_scheduler_instance

        scheduler.start()

        # Only dependency_check should be registered
        assert mock_scheduler_instance.add_job.call_count == 1
        call_kwargs = mock_scheduler_instance.add_job.call_args_list[0].kwargs
        assert call_kwargs["id"] == "dependency_check"

    @pytest.mark.asyncio
    async def test_stop_shuts_down_scheduler(self) -> None:
        config = _make_daemon_config()
        queue = MagicMock(spec=TaskQueue)
        scheduler = DaemonScheduler(config, queue)
        scheduler._scheduler = MagicMock()

        await scheduler.stop()

        scheduler._scheduler is None

    @pytest.mark.asyncio
    async def test_stop_noop_when_not_started(self) -> None:
        config = _make_daemon_config()
        queue = MagicMock(spec=TaskQueue)
        scheduler = DaemonScheduler(config, queue)

        await scheduler.stop()  # Should not raise

    def test_get_jobs_returns_empty_when_not_started(self) -> None:
        config = _make_daemon_config()
        queue = MagicMock(spec=TaskQueue)
        scheduler = DaemonScheduler(config, queue)

        assert scheduler.get_jobs() == []

    def test_get_jobs_returns_job_info(self) -> None:
        config = _make_daemon_config()
        queue = MagicMock(spec=TaskQueue)
        scheduler = DaemonScheduler(config, queue)

        mock_job = MagicMock()
        mock_job.id = "nightly_scan"
        mock_job.name = "Nightly repository scan"
        mock_job.next_run_time = None

        mock_scheduler = MagicMock()
        mock_scheduler.get_jobs.return_value = [mock_job]
        scheduler._scheduler = mock_scheduler

        jobs = scheduler.get_jobs()
        assert len(jobs) == 1
        assert jobs[0]["id"] == "nightly_scan"
        assert jobs[0]["name"] == "Nightly repository scan"
        assert jobs[0]["next_run"] is None

    @pytest.mark.asyncio
    async def test_nightly_scan_submits_task(self) -> None:
        config = _make_daemon_config()
        queue = MagicMock(spec=TaskQueue)
        queue.submit = AsyncMock(return_value="task-id")
        scheduler = DaemonScheduler(config, queue)

        await scheduler._nightly_scan()

        queue.submit.assert_awaited_once()
        submitted = queue.submit.call_args[0][0]
        assert submitted.project_id == "scheduler"
        assert submitted.tier_override == "free"
        assert submitted.budget_limit_usd == 1.0
        assert submitted.max_iterations == 10

    @pytest.mark.asyncio
    async def test_dependency_check_submits_task(self) -> None:
        config = _make_daemon_config()
        queue = MagicMock(spec=TaskQueue)
        queue.submit = AsyncMock(return_value="task-id")
        scheduler = DaemonScheduler(config, queue)

        await scheduler._dependency_check()

        queue.submit.assert_awaited_once()
        submitted = queue.submit.call_args[0][0]
        assert submitted.project_id == "scheduler"
        assert submitted.tier_override == "standard"
        assert submitted.budget_limit_usd == 2.0
        assert submitted.max_iterations == 15
