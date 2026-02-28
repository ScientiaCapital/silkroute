"""Tool audit log persistence — INSERT tool call records.

Maps tool call data from agent iterations to the ``tool_audit_log`` table
defined in ``sql/init.sql``. Follows the same fire-and-forget pattern
as cost_logs.py.
"""

from __future__ import annotations

import json

import asyncpg
import structlog

from silkroute.agent.session import AgentSession, Iteration

log = structlog.get_logger()

# Truncate tool output to avoid bloating the audit table
_MAX_OUTPUT_LENGTH = 2000


async def insert_tool_audit_logs(
    pool: asyncpg.Pool,
    session: AgentSession,
    iteration: Iteration,
) -> None:
    """INSERT tool audit log rows for all tool calls in an iteration.

    Skips silently if the iteration has no tool calls.
    """
    if not iteration.tool_calls:
        return

    rows = [
        (
            session.id,
            tc.tool_name,
            json.dumps(tc.tool_input),
            tc.tool_output[:_MAX_OUTPUT_LENGTH],
            tc.success,
            tc.error_message,
            tc.duration_ms,
        )
        for tc in iteration.tool_calls
    ]

    await pool.executemany(
        """
        INSERT INTO tool_audit_log (session_id, tool_name, tool_input,
                                     tool_output, success, error_message,
                                     duration_ms)
        VALUES ($1, $2, $3::jsonb, $4, $5, $6, $7)
        """,
        rows,
    )
    log.debug(
        "db_tool_audit_inserted",
        session_id=session.id,
        iteration=iteration.number,
        count=len(rows),
    )
