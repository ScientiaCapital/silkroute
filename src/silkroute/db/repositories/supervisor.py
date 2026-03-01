"""Supervisor session persistence — CRUD for supervisor_sessions table.

Follows the pool-based function pattern established by cost_logs.py
and tool_audit.py. All functions take an asyncpg.Pool as the first arg.
"""

from __future__ import annotations

import json

import asyncpg
import structlog

from silkroute.mantis.supervisor.models import (
    SessionStatus,
    SupervisorCheckpoint,
    SupervisorPlan,
    SupervisorSession,
)

log = structlog.get_logger()


async def create_supervisor_session(
    pool: asyncpg.Pool,
    session: SupervisorSession,
) -> None:
    """INSERT a new supervisor session."""
    await pool.execute(
        """
        INSERT INTO supervisor_sessions
            (id, project_id, status, plan_json, context_json,
             total_cost_usd, config_json, error)
        VALUES ($1, $2, $3, $4::jsonb, $5::jsonb, $6, $7::jsonb, $8)
        """,
        session.id,
        session.project_id,
        session.status.value,
        json.dumps(session.plan.to_dict()),
        json.dumps(session.plan.context),
        session.total_cost_usd,
        json.dumps(session.config_json),
        session.error,
    )
    log.debug("db_supervisor_session_created", session_id=session.id)


async def update_supervisor_session(
    pool: asyncpg.Pool,
    session: SupervisorSession,
) -> None:
    """UPDATE an existing supervisor session."""
    await pool.execute(
        """
        UPDATE supervisor_sessions
        SET status = $2, plan_json = $3::jsonb, context_json = $4::jsonb,
            total_cost_usd = $5, error = $6, updated_at = NOW()
        WHERE id = $1
        """,
        session.id,
        session.status.value,
        json.dumps(session.plan.to_dict()),
        json.dumps(session.plan.context),
        session.total_cost_usd,
        session.error,
    )
    log.debug("db_supervisor_session_updated", session_id=session.id)


async def get_supervisor_session(
    pool: asyncpg.Pool,
    session_id: str,
) -> SupervisorSession | None:
    """SELECT a supervisor session by ID. Returns None if not found."""
    row = await pool.fetchrow(
        "SELECT * FROM supervisor_sessions WHERE id = $1",
        session_id,
    )
    if row is None:
        return None
    return _row_to_session(row)


async def update_checkpoint(
    pool: asyncpg.Pool,
    session_id: str,
    checkpoint: SupervisorCheckpoint,
    total_cost_usd: float,
) -> None:
    """UPDATE checkpoint and cost for a session."""
    checkpoint_json = {
        "session_id": checkpoint.session_id,
        "plan_json": checkpoint.plan_json,
        "context_json": checkpoint.context_json,
        "step_results": checkpoint.step_results,
        "total_cost_usd": checkpoint.total_cost_usd,
        "created_at": checkpoint.created_at.isoformat(),
    }
    await pool.execute(
        """
        UPDATE supervisor_sessions
        SET checkpoint_json = $2::jsonb, total_cost_usd = $3, updated_at = NOW()
        WHERE id = $1
        """,
        session_id,
        json.dumps(checkpoint_json),
        total_cost_usd,
    )
    log.debug("db_supervisor_checkpoint_updated", session_id=session_id)


async def list_supervisor_sessions(
    pool: asyncpg.Pool,
    project_id: str | None = None,
    status: str | None = None,
    limit: int = 50,
) -> list[SupervisorSession]:
    """SELECT supervisor sessions with optional filters."""
    query = "SELECT * FROM supervisor_sessions WHERE 1=1"
    params: list = []
    idx = 1

    if project_id is not None:
        query += f" AND project_id = ${idx}"
        params.append(project_id)
        idx += 1

    if status is not None:
        query += f" AND status = ${idx}"
        params.append(status)
        idx += 1

    query += f" ORDER BY created_at DESC LIMIT ${idx}"
    params.append(limit)

    rows = await pool.fetch(query, *params)
    return [_row_to_session(r) for r in rows]


async def delete_supervisor_session(
    pool: asyncpg.Pool,
    session_id: str,
) -> bool:
    """DELETE a supervisor session. Returns True if a row was deleted."""
    result = await pool.execute(
        "DELETE FROM supervisor_sessions WHERE id = $1",
        session_id,
    )
    deleted = result == "DELETE 1"
    if deleted:
        log.debug("db_supervisor_session_deleted", session_id=session_id)
    return deleted


def _row_to_session(row: asyncpg.Record) -> SupervisorSession:
    """Convert a DB row to a SupervisorSession."""
    plan_raw = row["plan_json"]
    plan_data = plan_raw if isinstance(plan_raw, dict) else json.loads(plan_raw)
    ctx_raw = row["context_json"]
    context_data = ctx_raw if isinstance(ctx_raw, dict) else json.loads(ctx_raw)

    plan = SupervisorPlan.from_dict(plan_data)
    plan.context = context_data

    checkpoint = None
    if row["checkpoint_json"]:
        cp_raw = row["checkpoint_json"]
        cp_data = cp_raw if isinstance(cp_raw, dict) else json.loads(cp_raw)
        checkpoint = SupervisorCheckpoint(
            session_id=cp_data.get("session_id", ""),
            plan_json=cp_data.get("plan_json", {}),
            context_json=cp_data.get("context_json", {}),
            step_results=cp_data.get("step_results", {}),
            total_cost_usd=cp_data.get("total_cost_usd", 0.0),
        )

    return SupervisorSession(
        id=row["id"],
        project_id=row["project_id"],
        status=SessionStatus(row["status"]),
        plan=plan,
        checkpoint=checkpoint,
        total_cost_usd=float(row["total_cost_usd"]),
        config_json=(
            row["config_json"]
            if isinstance(row["config_json"], dict)
            else json.loads(row["config_json"])
        ),
        created_at=row["created_at"],
        updated_at=row["updated_at"],
        error=row["error"] or "",
    )
