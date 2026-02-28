"""FastAPI application factory for SilkRoute REST API.

Uses a create_app() factory for testability — each test gets a fresh app
with custom dependency overrides. The lifespan context manager handles
Redis and DB pool lifecycle.
"""

from __future__ import annotations

from collections.abc import AsyncIterator
from contextlib import asynccontextmanager

import redis.asyncio as aioredis
import structlog
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from silkroute import __version__
from silkroute.config.settings import SilkRouteSettings
from silkroute.daemon.queue import TaskQueue

log = structlog.get_logger()


@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncIterator[None]:
    """Manage Redis and DB pool connections for the API lifetime."""
    settings: SilkRouteSettings = app.state.settings

    # Connect Redis
    try:
        redis = aioredis.from_url(
            settings.database.redis_url,
            decode_responses=True,
            max_connections=10,
        )
        await redis.ping()
        app.state.redis = redis
        app.state.queue = TaskQueue(redis, maxsize=settings.api.queue_maxsize)
        await app.state.queue.init_counters()
        log.info("api_redis_connected")
    except (aioredis.ConnectionError, aioredis.TimeoutError, OSError) as exc:
        log.warning("api_redis_failed", error=str(exc))
        app.state.redis = None
        app.state.queue = None

    # Connect Postgres (optional — budget queries degrade gracefully)
    try:
        import asyncpg

        pool = await asyncpg.create_pool(
            settings.database.postgres_url,
            min_size=1,
            max_size=5,
            command_timeout=10,
        )
        app.state.db_pool = pool
        log.info("api_db_connected")
    except Exception as exc:
        log.warning("api_db_failed", error=str(exc))
        app.state.db_pool = None

    yield

    # Cleanup
    if getattr(app.state, "redis", None) is not None:
        await app.state.redis.aclose()
        log.info("api_redis_closed")
    if getattr(app.state, "db_pool", None) is not None:
        await app.state.db_pool.close()
        log.info("api_db_closed")


def create_app(settings: SilkRouteSettings | None = None) -> FastAPI:
    """Create and configure the FastAPI application.

    Args:
        settings: Override settings (used in tests). If None, loads from env.
    """
    if settings is None:
        from silkroute.config.settings import load_settings

        settings = load_settings()

    app = FastAPI(
        title="SilkRoute API",
        description="AI agent orchestrator for Chinese LLMs",
        version=__version__,
        lifespan=lifespan,
    )
    app.state.settings = settings

    # CORS for dashboard
    app.add_middleware(
        CORSMiddleware,
        allow_origins=settings.api.cors_origins,
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )

    # Register routers
    from silkroute.api.routes.budget import router as budget_router
    from silkroute.api.routes.health import router as health_router
    from silkroute.api.routes.models_api import router as models_router
    from silkroute.api.routes.runtime import router as runtime_router
    from silkroute.api.routes.tasks import router as tasks_router

    app.include_router(health_router)
    app.include_router(tasks_router)
    app.include_router(runtime_router)
    app.include_router(models_router)
    app.include_router(budget_router)

    return app
