"""Cost log persistence — INSERT per-iteration LLM cost records.

Maps iteration data + model metadata to the ``cost_logs`` table
defined in ``sql/init.sql``.
"""

from __future__ import annotations

import asyncpg
import structlog

from silkroute.agent.session import AgentSession, Iteration
from silkroute.providers.models import ModelSpec

log = structlog.get_logger()


async def insert_cost_log(
    pool: asyncpg.Pool,
    session: AgentSession,
    iteration: Iteration,
    model: ModelSpec,
) -> None:
    """INSERT a cost log row for one agent iteration."""
    await pool.execute(
        """
        INSERT INTO cost_logs (project_id, model_id, model_tier, provider,
                               input_tokens, output_tokens, total_tokens,
                               cost_usd, task_type, session_id, latency_ms)
        VALUES ($1, $2, $3, $4, $5, $6, $7, $8, $9, $10, $11)
        """,
        session.project_id,
        model.model_id,
        model.tier.value,
        model.provider.value,
        iteration.input_tokens,
        iteration.output_tokens,
        iteration.input_tokens + iteration.output_tokens,
        iteration.cost_usd,
        session.task[:100],  # task_type column, truncated
        session.id,
        iteration.latency_ms,
    )
    log.debug(
        "db_cost_log_inserted",
        session_id=session.id,
        iteration=iteration.number,
        cost_usd=iteration.cost_usd,
    )
