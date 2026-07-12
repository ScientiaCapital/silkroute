"""Model cost snapshot rollup persistence — UPSERT and query for
model_cost_snapshots table.

Follows the pool-based function pattern established by budget_snapshots.py,
but grouped by (project_id, model_id, provider) instead of just project_id/tier
— this is the per-model view budget_snapshots deliberately doesn't provide.
"""

from __future__ import annotations

import datetime
from typing import Any

import asyncpg
import structlog

log = structlog.get_logger()


async def rollup_day(pool: asyncpg.Pool, date: datetime.date) -> None:
    """UPSERT a daily per-model rollup for all projects for the given date.

    Aggregates cost_logs rows for the given calendar day, grouped by
    project_id, model_id, and provider, and upserts into
    model_cost_snapshots.  Safe to call multiple times — idempotent.
    """
    await pool.execute(
        """
        INSERT INTO model_cost_snapshots (
            project_id, model_id, provider, snapshot_date,
            total_cost_usd, total_requests, total_tokens
        )
        SELECT
            project_id,
            model_id,
            provider,
            $1::date,
            SUM(cost_usd),
            COUNT(*),
            SUM(total_tokens)
        FROM cost_logs
        WHERE created_at >= $1::date AND created_at < $1::date + INTERVAL '1 day'
        GROUP BY project_id, model_id, provider
        ON CONFLICT (project_id, model_id, provider, snapshot_date) DO UPDATE SET
            total_cost_usd = EXCLUDED.total_cost_usd,
            total_requests = EXCLUDED.total_requests,
            total_tokens = EXCLUDED.total_tokens
        """,
        date,
    )
    log.debug("db_model_cost_snapshot_rolled_up", date=str(date))


async def get_snapshots(
    pool: asyncpg.Pool,
    project_id: str,
    start_date: datetime.date,
    end_date: datetime.date,
) -> list[dict[str, Any]]:
    """SELECT per-model cost snapshots for a project within [start_date, end_date] inclusive."""
    rows = await pool.fetch(
        """
        SELECT *
        FROM model_cost_snapshots
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
