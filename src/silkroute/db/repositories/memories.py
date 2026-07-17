"""Persistent agent memory — INSERT/SELECT/DELETE for the agent_memories table.

Follows the pool-based function pattern established by skill_executions.py.
All functions take an asyncpg.Pool as the first arg.
"""

from __future__ import annotations

from typing import Any

import asyncpg
import structlog

log = structlog.get_logger()

_MAX_CONTENT_CHARS = 500


async def insert_memory(
    pool: asyncpg.Pool,
    content: str,
    *,
    kind: str = "fact",
    project_id: str | None = None,
    importance: float = 0.5,
    source_session_id: str | None = None,
) -> dict[str, Any]:
    """INSERT a memory, or bump importance if identical content already exists in scope.

    Dedup is keyed on (project_id, md5(content)) via the idx_agent_memories_dedup
    unique index — the same fact remembered twice in the same scope updates
    importance instead of creating a duplicate row.
    """
    content = content[:_MAX_CONTENT_CHARS]
    token_estimate = max(1, len(content) // 4)
    row = await pool.fetchrow(
        """
        INSERT INTO agent_memories
            (project_id, kind, content, importance, source_session_id, token_estimate)
        VALUES ($1, $2, $3, $4, $5, $6)
        ON CONFLICT (COALESCE(project_id, ''), md5(content))
        DO UPDATE SET
            importance = GREATEST(agent_memories.importance, EXCLUDED.importance),
            updated_at = NOW()
        RETURNING *
        """,
        project_id,
        kind,
        content,
        importance,
        source_session_id,
        token_estimate,
    )
    log.debug("db_memory_inserted", project_id=project_id, kind=kind)
    return dict(row)


async def list_memories(
    pool: asyncpg.Pool,
    *,
    project_id: str | None = None,
    kind: str | None = None,
    limit: int = 50,
) -> list[dict[str, Any]]:
    """SELECT memories with optional scope/kind filters, newest first."""
    query = "SELECT * FROM agent_memories WHERE 1=1"
    params: list[Any] = []
    idx = 1

    if project_id is not None:
        query += f" AND project_id = ${idx}"
        params.append(project_id)
        idx += 1

    if kind is not None:
        query += f" AND kind = ${idx}"
        params.append(kind)
        idx += 1

    query += f" ORDER BY created_at DESC LIMIT ${idx}"
    params.append(limit)

    rows = await pool.fetch(query, *params)
    return [dict(r) for r in rows]


async def recall_memories(
    pool: asyncpg.Pool,
    project_id: str,
    *,
    limit: int = 8,
) -> list[dict[str, Any]]:
    """SELECT the top memories for a session: project-scoped + global, most important first."""
    rows = await pool.fetch(
        """
        SELECT * FROM agent_memories
        WHERE project_id = $1 OR project_id IS NULL
        ORDER BY importance DESC, created_at DESC
        LIMIT $2
        """,
        project_id,
        limit,
    )
    return [dict(r) for r in rows]


async def mark_recalled(pool: asyncpg.Pool, memory_ids: list[int]) -> None:
    """Bump recall_count and last_recalled_at for a batch of recalled memories."""
    if not memory_ids:
        return
    await pool.execute(
        """
        UPDATE agent_memories
        SET recall_count = recall_count + 1, last_recalled_at = NOW()
        WHERE id = ANY($1::bigint[])
        """,
        memory_ids,
    )


async def delete_memory(pool: asyncpg.Pool, memory_id: int) -> bool:
    """DELETE a memory by id. Returns True if a row was deleted."""
    row = await pool.fetchrow(
        "DELETE FROM agent_memories WHERE id = $1 RETURNING id",
        memory_id,
    )
    return row is not None
