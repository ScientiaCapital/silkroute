"""Project budget queries — lookup budget caps and monthly spend.

Reads from the ``projects`` table and ``v_budget_remaining`` view
defined in ``sql/init.sql``.
"""

from __future__ import annotations

import asyncpg
import structlog

log = structlog.get_logger()


async def get_project_budget(pool: asyncpg.Pool, project_id: str) -> float | None:
    """Fetch the monthly budget cap for a project.

    Returns None if the project doesn't exist (caller uses session default).
    """
    row = await pool.fetchrow(
        "SELECT budget_monthly_usd FROM projects WHERE id = $1",
        project_id,
    )
    if row is None:
        return None
    return float(row["budget_monthly_usd"])


async def get_monthly_spend(pool: asyncpg.Pool, project_id: str) -> float:
    """Query actual monthly spend for a project from the budget view.

    Returns 0.0 if the project has no cost records this month.
    """
    row = await pool.fetchrow(
        "SELECT COALESCE(spent_this_month, 0) AS spent "
        "FROM v_budget_remaining WHERE project_id = $1",
        project_id,
    )
    if row is None:
        return 0.0
    return float(row["spent"])


async def get_daily_spend(pool: asyncpg.Pool, project_id: str) -> float:
    """Query today's spend for a project from cost_logs.

    Returns 0.0 if no cost records today.
    """
    row = await pool.fetchrow(
        "SELECT COALESCE(SUM(cost_usd), 0) AS spent "
        "FROM cost_logs WHERE project_id = $1 AND created_at >= CURRENT_DATE",
        project_id,
    )
    if row is None:
        return 0.0
    return float(row["spent"])


async def get_hourly_spend_rate(pool: asyncpg.Pool, project_id: str) -> float:
    """Query the average hourly spend rate over the last hour.

    Used by the circuit breaker to detect runaway spending.
    Returns 0.0 if no cost records in the last hour.
    """
    row = await pool.fetchrow(
        "SELECT COALESCE(SUM(cost_usd), 0) AS spent "
        "FROM cost_logs WHERE project_id = $1 "
        "AND created_at >= NOW() - INTERVAL '1 hour'",
        project_id,
    )
    if row is None:
        return 0.0
    return float(row["spent"])
