"""AgentSession persistence — INSERT, UPDATE, and CLOSE operations.

Maps the in-memory AgentSession dataclass to the ``agent_sessions`` table
defined in ``sql/init.sql``.

Critical mapping note:
    SessionStatus.BUDGET_EXCEEDED has no DB equivalent — the CHECK constraint
    only allows ('active', 'completed', 'failed', 'timeout'). We map
    BUDGET_EXCEEDED → 'failed' at this boundary.
"""

from __future__ import annotations

import json
from datetime import UTC, datetime

import asyncpg
import structlog

from silkroute.agent.session import AgentSession, SessionStatus

log = structlog.get_logger()

# DB CHECK constraint only allows these 4 values.
# BUDGET_EXCEEDED is mapped to 'failed' at the DB boundary.
_STATUS_TO_DB: dict[SessionStatus, str] = {
    SessionStatus.ACTIVE: "active",
    SessionStatus.COMPLETED: "completed",
    SessionStatus.FAILED: "failed",
    SessionStatus.TIMEOUT: "timeout",
    SessionStatus.BUDGET_EXCEEDED: "failed",
}


async def create_session(pool: asyncpg.Pool, session: AgentSession) -> None:
    """INSERT a new agent session row."""
    await pool.execute(
        """
        INSERT INTO agent_sessions (id, project_id, status, task, model_id,
                                    iteration_count, total_cost_usd,
                                    messages_json, started_at, updated_at)
        VALUES ($1, $2, $3, $4, $5, $6, $7, $8::jsonb, $9, $10)
        """,
        session.id,
        session.project_id,
        _STATUS_TO_DB[session.status],
        session.task,
        session.model_id,
        session.iteration_count,
        session.total_cost_usd,
        json.dumps(session.messages),
        session.started_at,
        datetime.now(UTC),
    )
    log.debug("db_session_created", session_id=session.id)


async def update_session(pool: asyncpg.Pool, session: AgentSession) -> None:
    """UPDATE session with latest iteration state."""
    await pool.execute(
        """
        UPDATE agent_sessions
        SET iteration_count = $2,
            total_cost_usd  = $3,
            messages_json   = $4::jsonb,
            updated_at      = $5
        WHERE id = $1
        """,
        session.id,
        session.iteration_count,
        session.total_cost_usd,
        json.dumps(session.messages),
        datetime.now(UTC),
    )
    log.debug("db_session_updated", session_id=session.id, iterations=session.iteration_count)


async def close_session(pool: asyncpg.Pool, session: AgentSession) -> None:
    """UPDATE session with terminal status and completed_at timestamp."""
    await pool.execute(
        """
        UPDATE agent_sessions
        SET status         = $2,
            iteration_count = $3,
            total_cost_usd  = $4,
            messages_json   = $5::jsonb,
            completed_at    = $6,
            updated_at      = $7
        WHERE id = $1
        """,
        session.id,
        _STATUS_TO_DB[session.status],
        session.iteration_count,
        session.total_cost_usd,
        json.dumps(session.messages),
        session.completed_at or datetime.now(UTC),
        datetime.now(UTC),
    )
    log.debug("db_session_closed", session_id=session.id, status=session.status.value)
