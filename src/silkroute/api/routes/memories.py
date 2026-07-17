"""Memory endpoints — inspect and manage persistent agent memory.

GET /memories           → list memories (optional project_id/kind/limit filters)
DELETE /memories/{id}   → forget a memory

GET fails open if Postgres is unavailable (returns available=false, not 503).
DELETE returns 503 if Postgres is unavailable — a delete must not silently no-op.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

from fastapi import APIRouter, Depends, HTTPException, Query

from silkroute.api.auth import require_auth
from silkroute.api.deps import get_db_pool
from silkroute.api.models import MemoryItem, MemoryListResponse

if TYPE_CHECKING:
    import asyncpg

router = APIRouter(prefix="/memories", tags=["memories"], dependencies=[Depends(require_auth)])


@router.get("")
async def list_memories_route(
    project_id: str | None = Query(default=None, description="Filter to a project's memories"),
    kind: str | None = Query(default=None, description="Filter by kind (fact/preference/outcome)"),
    limit: int = Query(default=50, le=200),
    db_pool: asyncpg.Pool | None = Depends(get_db_pool),
) -> MemoryListResponse:
    """List persistent memories. Fails open if Postgres is unavailable."""
    if db_pool is None:
        return MemoryListResponse(items=[], count=0, available=False)

    try:
        from silkroute.db.repositories.memories import list_memories

        rows = await list_memories(db_pool, project_id=project_id, kind=kind, limit=limit)
    except Exception:
        return MemoryListResponse(items=[], count=0, available=False)

    items = [
        MemoryItem(
            id=int(row["id"]),
            project_id=row["project_id"],
            kind=str(row["kind"]),
            content=str(row["content"]),
            importance=float(row["importance"]),
            recall_count=int(row["recall_count"]),
            created_at=str(row["created_at"]),
        )
        for row in rows
    ]
    return MemoryListResponse(items=items, count=len(items))


@router.delete("/{memory_id}")
async def forget_memory_route(
    memory_id: int,
    db_pool: asyncpg.Pool | None = Depends(get_db_pool),
) -> dict[str, bool]:
    """Delete a memory by id. 404 if it doesn't exist, 503 if Postgres is unavailable."""
    if db_pool is None:
        raise HTTPException(status_code=503, detail="Memory store unavailable")

    from silkroute.db.repositories.memories import delete_memory

    deleted = await delete_memory(db_pool, memory_id)
    if not deleted:
        raise HTTPException(status_code=404, detail="Memory not found")
    return {"deleted": True}
