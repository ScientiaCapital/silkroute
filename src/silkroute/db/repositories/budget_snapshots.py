"""Budget snapshot rollup persistence — UPSERT and query for budget_snapshots table.

Follows the pool-based function pattern established by skill_executions.py.
All functions take an asyncpg.Pool as the first arg.
"""

from __future__ import annotations

import datetime
from typing import Any

import asyncpg
import structlog

log = structlog.get_logger()


async def rollup_day(pool: asyncpg.Pool, date: datetime.date) -> None:
    """UPSERT a daily rollup for all projects for the given date.

    Aggregates cost_logs rows for the given calendar day, grouped by project_id,
    and upserts into budget_snapshots.  Safe to call multiple times — idempotent.
    """
    await pool.execute(
        """
        INSERT INTO budget_snapshots (
            project_id, snapshot_date,
            total_cost_usd, total_requests, total_tokens,
            free_requests, free_cost_usd,
            standard_requests, standard_cost_usd,
            premium_requests, premium_cost_usd
        )
        SELECT
            project_id,
            $1::date,
            SUM(cost_usd),
            COUNT(*),
            SUM(total_tokens),
            COUNT(*) FILTER (WHERE model_tier = 'free'),
            COALESCE(SUM(cost_usd) FILTER (WHERE model_tier = 'free'), 0),
            COUNT(*) FILTER (WHERE model_tier = 'standard'),
            COALESCE(SUM(cost_usd) FILTER (WHERE model_tier = 'standard'), 0),
            COUNT(*) FILTER (WHERE model_tier = 'premium'),
            COALESCE(SUM(cost_usd) FILTER (WHERE model_tier = 'premium'), 0)
        FROM cost_logs
        WHERE created_at >= $1::date AND created_at < $1::date + INTERVAL '1 day'
        GROUP BY project_id
        ON CONFLICT (project_id, snapshot_date) DO UPDATE SET
            total_cost_usd = EXCLUDED.total_cost_usd,
            total_requests = EXCLUDED.total_requests,
            total_tokens = EXCLUDED.total_tokens,
            free_requests = EXCLUDED.free_requests,
            free_cost_usd = EXCLUDED.free_cost_usd,
            standard_requests = EXCLUDED.standard_requests,
            standard_cost_usd = EXCLUDED.standard_cost_usd,
            premium_requests = EXCLUDED.premium_requests,
            premium_cost_usd = EXCLUDED.premium_cost_usd
        """,
        date,
    )
    log.debug("db_budget_snapshot_rolled_up", date=str(date))


async def get_snapshots(
    pool: asyncpg.Pool,
    project_id: str,
    start_date: datetime.date,
    end_date: datetime.date,
) -> list[dict[str, Any]]:
    """SELECT budget snapshots for a project within [start_date, end_date] inclusive."""
    rows = await pool.fetch(
        """
        SELECT *
        FROM budget_snapshots
        WHERE project_id = $1
          AND snapshot_date >= $2
          AND snapshot_date <= $3
        ORDER BY snapshot_date ASC
        """,
        project_id,
        start_date,
        end_date,
    )
    return [dict(r) for r in rows]


async def backfill(
    pool: asyncpg.Pool,
    start_date: datetime.date,
    end_date: datetime.date,
) -> int:
    """Backfill daily rollups for every day in [start_date, end_date] inclusive.

    Calls rollup_day sequentially for each day.  Returns the number of days processed.
    """
    days_processed = 0
    current = start_date
    while current <= end_date:
        await rollup_day(pool, current)
        current += datetime.timedelta(days=1)
        days_processed += 1
    log.info(
        "db_budget_snapshot_backfill_done",
        start_date=str(start_date),
        end_date=str(end_date),
        days_processed=days_processed,
    )
    return days_processed
