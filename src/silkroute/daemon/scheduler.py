"""Daemon scheduler — APScheduler cron jobs with Redis job store.

Registers nightly scan and weekly dependency audit jobs that submit
tasks directly to the daemon's TaskQueue.
"""

from __future__ import annotations

from urllib.parse import urlparse

import structlog
from apscheduler.jobstores.redis import RedisJobStore
from apscheduler.schedulers.asyncio import AsyncIOScheduler
from apscheduler.triggers.cron import CronTrigger

from silkroute.config.settings import DaemonConfig, DatabaseConfig
from silkroute.daemon.queue import TaskQueue, TaskRequest

log = structlog.get_logger()


class DaemonScheduler:
    """APScheduler wrapper that manages cron jobs for the daemon.

    Uses a Redis job store so scheduled jobs persist across daemon restarts.
    Built-in jobs: nightly repository scan, weekly dependency audit.
    """

    def __init__(self, config: DaemonConfig, queue: TaskQueue) -> None:
        self._config = config
        self._queue = queue
        self._scheduler: AsyncIOScheduler | None = None

    def start(self) -> None:
        """Create the AsyncIOScheduler with Redis job store and register jobs."""
        db_cfg = DatabaseConfig()
        parsed = urlparse(db_cfg.redis_url)

        jobstore = RedisJobStore(
            host=parsed.hostname or "localhost",
            port=parsed.port or 6379,
            db=int(parsed.path.lstrip("/") or "0"),
            jobs_key="silkroute:scheduler:jobs",
            run_times_key="silkroute:scheduler:run_times",
        )

        self._scheduler = AsyncIOScheduler(
            jobstores={"default": jobstore},
            job_defaults={
                "coalesce": True,
                "max_instances": 1,
                "replace_existing": True,
            },
        )

        # Register built-in cron jobs
        if self._config.nightly_scan_enabled:
            self._scheduler.add_job(
                self._nightly_scan,
                trigger=CronTrigger.from_crontab(self._config.nightly_scan_cron),
                id="nightly_scan",
                name="Nightly repository scan",
                replace_existing=True,
            )
            log.info(
                "scheduler_job_registered",
                job_id="nightly_scan",
                cron=self._config.nightly_scan_cron,
            )

        self._scheduler.add_job(
            self._dependency_check,
            trigger=CronTrigger.from_crontab(self._config.dependency_check_cron),
            id="dependency_check",
            name="Weekly dependency audit",
            replace_existing=True,
        )
        log.info(
            "scheduler_job_registered",
            job_id="dependency_check",
            cron=self._config.dependency_check_cron,
        )

        self._scheduler.start()
        log.info("scheduler_started", job_count=len(self._scheduler.get_jobs()))

    async def stop(self) -> None:
        """Shut down the scheduler."""
        if self._scheduler is not None:
            self._scheduler.shutdown(wait=False)
            self._scheduler = None
            log.info("scheduler_stopped")

    def get_jobs(self) -> list[dict]:
        """Return a list of registered jobs for status reporting."""
        if self._scheduler is None:
            return []
        return [
            {
                "id": job.id,
                "name": job.name,
                "next_run": job.next_run_time.isoformat() if job.next_run_time else None,
            }
            for job in self._scheduler.get_jobs()
        ]

    async def _nightly_scan(self) -> None:
        """Submit a nightly repository scan task to the queue."""
        log.info("scheduler_nightly_scan_triggered")
        request = TaskRequest(
            task="Scan all tracked repositories for issues, stale PRs, and code quality",
            project_id="scheduler",
            tier_override="free",
            budget_limit_usd=1.0,
            max_iterations=10,
        )
        await self._queue.submit(request)

    async def _dependency_check(self) -> None:
        """Submit a weekly dependency audit task to the queue."""
        log.info("scheduler_dependency_check_triggered")
        request = TaskRequest(
            task="Audit all project dependencies for security vulnerabilities and updates",
            project_id="scheduler",
            tier_override="standard",
            budget_limit_usd=2.0,
            max_iterations=15,
        )
        await self._queue.submit(request)
