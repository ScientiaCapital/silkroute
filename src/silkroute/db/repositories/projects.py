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


async def create_project(
    pool: asyncpg.Pool,
    project_id: str,
    name: str,
    description: str = "",
    github_repo: str = "",
    budget_monthly_usd: float = 2.85,
    budget_daily_usd: float = 0.10,
) -> dict:
    """Insert a new project row and return it as a dict."""
    row = await pool.fetchrow(
        "INSERT INTO projects (id, name, description, github_repo, "
        "budget_monthly_usd, budget_daily_usd) "
        "VALUES ($1, $2, $3, $4, $5, $6) RETURNING *",
        project_id,
        name,
        description,
        github_repo,
        budget_monthly_usd,
        budget_daily_usd,
    )
    return dict(row)


async def list_projects(pool: asyncpg.Pool) -> list[dict]:
    """Return all projects ordered by creation date (newest first)."""
    rows = await pool.fetch("SELECT * FROM projects ORDER BY created_at DESC")
    return [dict(r) for r in rows]


async def get_project(pool: asyncpg.Pool, project_id: str) -> dict | None:
    """Fetch a single project by ID, or None if not found."""
    row = await pool.fetchrow("SELECT * FROM projects WHERE id = $1", project_id)
    if row is None:
        return None
    return dict(row)


async def update_project(
    pool: asyncpg.Pool,
    project_id: str,
    *,
    name: str | None = None,
    description: str | None = None,
    github_repo: str | None = None,
    budget_monthly_usd: float | None = None,
    budget_daily_usd: float | None = None,
) -> dict | None:
    """Partially update a project. Returns updated dict or None if not found."""
    fields: list[str] = []
    values: list[object] = []
    idx = 1

    for col, val in [
        ("name", name),
        ("description", description),
        ("github_repo", github_repo),
        ("budget_monthly_usd", budget_monthly_usd),
        ("budget_daily_usd", budget_daily_usd),
    ]:
        if val is not None:
            idx += 1
            fields.append(f"{col} = ${idx}")
            values.append(val)

    if not fields:
        return await get_project(pool, project_id)

    fields.append("updated_at = NOW()")
    sql = f"UPDATE projects SET {', '.join(fields)} WHERE id = $1 RETURNING *"
    row = await pool.fetchrow(sql, project_id, *values)
    if row is None:
        return None
    return dict(row)


async def delete_project(pool: asyncpg.Pool, project_id: str) -> bool:
    """Delete a project by ID. Blocks deletion of 'default'. Returns True if deleted."""
    if project_id == "default":
        raise ValueError("Cannot delete the 'default' project")
    try:
        result = await pool.execute("DELETE FROM projects WHERE id = $1", project_id)
        return result == "DELETE 1"
    except asyncpg.ForeignKeyViolationError:
        raise ValueError(
            f"Cannot delete project '{project_id}': it has associated cost records"
        ) from None
