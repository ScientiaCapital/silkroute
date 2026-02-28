"""Health check endpoints — /health and /health/ready.

/health is a lightweight liveness probe (always succeeds).
/health/ready checks Redis and DB connectivity for readiness probes.
"""

from __future__ import annotations

from fastapi import APIRouter, Request

from silkroute import __version__

router = APIRouter(tags=["health"])


@router.get("/health")
async def health() -> dict:
    """Liveness probe — returns version and status."""
    return {
        "status": "ok",
        "version": __version__,
        "service": "silkroute-api",
    }


@router.get("/health/ready")
async def health_ready(request: Request) -> dict:
    """Readiness probe — checks Redis and DB connectivity."""
    checks: dict[str, str] = {}

    # Redis check
    redis = getattr(request.app.state, "redis", None)
    if redis is not None:
        try:
            await redis.ping()
            checks["redis"] = "ok"
        except Exception:
            checks["redis"] = "error"
    else:
        checks["redis"] = "unavailable"

    # DB check
    db_pool = getattr(request.app.state, "db_pool", None)
    if db_pool is not None:
        try:
            async with db_pool.acquire() as conn:
                await conn.fetchval("SELECT 1")
            checks["postgres"] = "ok"
        except Exception:
            checks["postgres"] = "error"
    else:
        checks["postgres"] = "unavailable"

    all_ok = all(v == "ok" for v in checks.values())
    return {
        "status": "ready" if all_ok else "degraded",
        "checks": checks,
    }
