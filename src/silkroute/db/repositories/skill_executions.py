"""Skill execution persistence — INSERT and query for skill_executions table.

Follows the pool-based function pattern established by supervisor.py.
All functions take an asyncpg.Pool as the first arg.
"""

from __future__ import annotations

import json
from typing import Any

import asyncpg
import structlog

log = structlog.get_logger()


async def insert_skill_execution(
    pool: asyncpg.Pool,
    skill_name: str,
    session_id: str,
    project_id: str,
    success: bool,
    cost_usd: float = 0.0,
    duration_ms: int = 0,
    input_json: dict[str, Any] | None = None,
    output_text: str = "",
    error_message: str = "",
) -> dict[str, Any]:
    """INSERT a skill execution record. Returns the inserted row as a dict."""
    row = await pool.fetchrow(
        """
        INSERT INTO skill_executions
            (skill_name, session_id, project_id, success, cost_usd,
             duration_ms, input_json, output_text, error_message)
        VALUES ($1, $2, $3, $4, $5, $6, $7::jsonb, $8, $9)
        RETURNING *
        """,
        skill_name,
        session_id,
        project_id,
        success,
        cost_usd,
        duration_ms,
        json.dumps(input_json or {}),
        output_text[:2000],
        error_message,
    )
    log.debug("db_skill_execution_inserted", skill_name=skill_name, session_id=session_id)
    return dict(row)


async def list_skill_executions(
    pool: asyncpg.Pool,
    skill_name: str | None = None,
    project_id: str | None = None,
    session_id: str | None = None,
    limit: int = 50,
) -> list[dict[str, Any]]:
    """SELECT skill executions with optional filters."""
    query = "SELECT * FROM skill_executions WHERE 1=1"
    params: list[Any] = []
    idx = 1

    if skill_name is not None:
        query += f" AND skill_name = ${idx}"
        params.append(skill_name)
        idx += 1

    if project_id is not None:
        query += f" AND project_id = ${idx}"
        params.append(project_id)
        idx += 1

    if session_id is not None:
        query += f" AND session_id = ${idx}"
        params.append(session_id)
        idx += 1

    query += f" ORDER BY created_at DESC LIMIT ${idx}"
    params.append(limit)

    rows = await pool.fetch(query, *params)
    return [dict(r) for r in rows]


async def get_skill_execution_stats(
    pool: asyncpg.Pool,
    project_id: str | None = None,
) -> list[dict[str, Any]]:
    """Aggregate stats grouped by skill_name: count, total_cost, avg_duration, success_rate."""
    if project_id is not None:
        rows = await pool.fetch(
            """
            SELECT skill_name,
                   COUNT(*) AS execution_count,
                   SUM(cost_usd) AS total_cost_usd,
                   AVG(duration_ms) AS avg_duration_ms,
                   AVG(CASE WHEN success THEN 1.0 ELSE 0.0 END) AS success_rate
            FROM skill_executions
            WHERE project_id = $1
            GROUP BY skill_name
            ORDER BY execution_count DESC
            """,
            project_id,
        )
    else:
        rows = await pool.fetch(
            """
            SELECT skill_name,
                   COUNT(*) AS execution_count,
                   SUM(cost_usd) AS total_cost_usd,
                   AVG(duration_ms) AS avg_duration_ms,
                   AVG(CASE WHEN success THEN 1.0 ELSE 0.0 END) AS success_rate
            FROM skill_executions
            GROUP BY skill_name
            ORDER BY execution_count DESC
            """,
        )
    return [dict(r) for r in rows]
