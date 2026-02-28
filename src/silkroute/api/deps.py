"""FastAPI dependency injection — Redis, TaskQueue, DB pool, settings.

All dependencies are injected via FastAPI's Depends() system, making them
easy to override in tests with app.dependency_overrides. No global mutable
state — everything flows through the lifespan-managed app.state.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

import redis.asyncio as aioredis
from fastapi import Depends, Request

from silkroute.config.settings import ApiConfig, BudgetConfig, SilkRouteSettings
from silkroute.daemon.queue import TaskQueue

if TYPE_CHECKING:
    import asyncpg


def get_settings(request: Request) -> SilkRouteSettings:
    """Retrieve settings from app state."""
    return request.app.state.settings


def get_api_config(settings: SilkRouteSettings = Depends(get_settings)) -> ApiConfig:
    """Retrieve API-specific config."""
    return settings.api


def get_budget_config(settings: SilkRouteSettings = Depends(get_settings)) -> BudgetConfig:
    """Retrieve budget config."""
    return settings.budget


def get_redis(request: Request) -> aioredis.Redis:
    """Retrieve the shared Redis client from app state.

    Raises 503 if Redis is unavailable (set during lifespan).
    """
    redis: aioredis.Redis | None = getattr(request.app.state, "redis", None)
    if redis is None:
        from fastapi import HTTPException

        raise HTTPException(status_code=503, detail="Redis unavailable")
    return redis


def get_queue(request: Request) -> TaskQueue:
    """Retrieve the TaskQueue from app state."""
    queue: TaskQueue | None = getattr(request.app.state, "queue", None)
    if queue is None:
        from fastapi import HTTPException

        raise HTTPException(status_code=503, detail="Task queue unavailable")
    return queue


def get_db_pool(request: Request) -> asyncpg.Pool | None:
    """Retrieve the DB connection pool (may be None if Postgres unavailable)."""
    return getattr(request.app.state, "db_pool", None)
