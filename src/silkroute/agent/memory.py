"""Persistent cross-session agent memory — recall, prompt formatting, and the
`remember` tool.

Fail-open, mirroring integrations/finops_client.py: a missing pool, disabled
config, or DB error must never break the agent loop — recall degrades to an
empty list and the `remember` tool simply isn't registered.
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Any

import structlog

from silkroute.agent.tools import ToolSpec

if TYPE_CHECKING:
    import asyncpg

    from silkroute.config.settings import MemoryConfig

log = structlog.get_logger()


async def recall_for_session(
    pool: asyncpg.Pool | None,
    project_id: str,
    cfg: MemoryConfig,
) -> list[dict[str, Any]]:
    """Recall the top memories for a new session, capped by cfg.recall_max_tokens.

    Returns [] if there's no pool, memory is disabled, or the DB errors —
    never raises.
    """
    if pool is None or not cfg.enabled:
        return []

    try:
        from silkroute.db.repositories.memories import recall_memories

        rows = await recall_memories(pool, project_id, limit=cfg.recall_limit)
    except Exception as exc:
        log.warning("memory_recall_failed", error=str(exc))
        return []

    kept: list[dict[str, Any]] = []
    token_total = 0
    for row in rows:
        tokens = int(row.get("token_estimate") or 0) or max(
            1, len(str(row.get("content", ""))) // 4
        )
        if token_total + tokens > cfg.recall_max_tokens:
            break
        kept.append(row)
        token_total += tokens
    return kept


def format_memory_block(memories: list[dict[str, Any]]) -> str:
    """Render recalled memories as a system-prompt section. Empty string if none."""
    if not memories:
        return ""
    lines = [f"- [{m['kind']}] {m['content']}" for m in memories]
    return "## Memory (from previous sessions)\n\n" + "\n".join(lines) + "\n"


def make_remember_tool(
    pool: asyncpg.Pool,
    project_id: str,
    session_id: str,
) -> ToolSpec:
    """Build the `remember` tool, bound to this session's pool and project.

    The handler never raises: DB errors are caught and returned as a string
    so a memory-store outage can't break the agent's turn.
    """

    async def _handle(
        content: str,
        kind: str = "fact",
        importance: float = 0.5,
        scope: str = "project",
    ) -> str:
        try:
            from silkroute.db.repositories.memories import insert_memory

            await insert_memory(
                pool,
                content,
                kind=kind,
                project_id=None if scope == "global" else project_id,
                importance=importance,
                source_session_id=session_id,
            )
            return "Memory saved."
        except Exception as exc:
            log.warning("remember_tool_failed", error=str(exc))
            return f"Error: could not save memory ({exc})"

    return ToolSpec(
        name="remember",
        description=(
            "Save a durable fact, user preference, or outcome that should be "
            "recalled in future sessions. Use for things worth remembering "
            "long-term (e.g. a stated preference or a notable result) — not "
            "for routine task details."
        ),
        parameters={
            "type": "object",
            "properties": {
                "content": {
                    "type": "string",
                    "description": "The fact, preference, or outcome to remember. Be concise.",
                },
                "kind": {
                    "type": "string",
                    "enum": ["fact", "preference", "outcome"],
                    "description": "Type of memory. Default: fact.",
                },
                "importance": {
                    "type": "number",
                    "description": "0.0-1.0, how important this is to recall later. Default: 0.5.",
                },
                "scope": {
                    "type": "string",
                    "enum": ["project", "global"],
                    "description": "'project' (default) scopes this to the current project; "
                    "'global' makes it recallable from any project.",
                },
            },
            "required": ["content"],
        },
        handler=_handle,
    )
