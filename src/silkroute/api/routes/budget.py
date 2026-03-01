"""Budget endpoints — global and per-project budget status.

GET /budget              → Global daily/monthly budget status
GET /budget/snapshots    → Daily budget snapshot history for a project
GET /budget/{project_id} → Per-project spend and limits

Fails open if Postgres is unavailable (returns zeros rather than 503).
"""

from __future__ import annotations

import datetime
from typing import TYPE_CHECKING

from fastapi import APIRouter, Depends, Query

from silkroute.api.auth import require_auth
from silkroute.api.deps import get_budget_config, get_db_pool
from silkroute.api.models import (
    BudgetSnapshotItem,
    BudgetSnapshotListResponse,
    GlobalBudgetResponse,
    ProjectBudgetResponse,
)
from silkroute.config.settings import BudgetConfig

if TYPE_CHECKING:
    import asyncpg

router = APIRouter(prefix="/budget", tags=["budget"], dependencies=[Depends(require_auth)])


@router.get("")
async def global_budget(
    budget_config: BudgetConfig = Depends(get_budget_config),
    db_pool: asyncpg.Pool | None = Depends(get_db_pool),
) -> GlobalBudgetResponse:
    """Get global budget status (daily + monthly + circuit breaker).

    Fails open if Postgres is unavailable — returns zero spend values.
    """
    daily_spent = 0.0
    monthly_spent = 0.0
    hourly_rate = 0.0

    if db_pool is not None:
        try:
            from silkroute.db.repositories.projects import (
                get_daily_spend,
                get_hourly_spend_rate,
                get_monthly_spend,
            )

            daily_spent = await get_daily_spend(db_pool, "default")
            monthly_spent = await get_monthly_spend(db_pool, "default")
            hourly_rate = await get_hourly_spend_rate(db_pool, "default")
        except Exception:
            pass  # Fail open

    from silkroute.agent.cost_guard import check_global_budget

    check = check_global_budget(
        daily_spent=daily_spent,
        monthly_spent=monthly_spent,
        hourly_rate=hourly_rate,
        budget_config=budget_config,
    )

    return GlobalBudgetResponse(
        daily_spent_usd=check.daily_spent_usd,
        daily_limit_usd=check.daily_limit_usd,
        monthly_spent_usd=check.monthly_spent_usd,
        monthly_limit_usd=check.monthly_limit_usd,
        hourly_rate_usd=check.hourly_rate_usd,
        allowed=check.allowed,
        warning=check.warning,
    )


@router.get("/snapshots")
async def budget_snapshots(
    project_id: str = Query(..., description="Project ID to fetch snapshots for"),
    start_date: datetime.date = Query(
        default=datetime.date.today() - datetime.timedelta(days=30),
        description="Inclusive start date (YYYY-MM-DD)",
    ),
    end_date: datetime.date = Query(
        default=datetime.date.today(),
        description="Inclusive end date (YYYY-MM-DD)",
    ),
    db_pool: asyncpg.Pool | None = Depends(get_db_pool),
) -> BudgetSnapshotListResponse:
    """Get daily budget snapshot history for a project.

    Fails open if Postgres is unavailable — returns an empty list.
    """
    if db_pool is None:
        return BudgetSnapshotListResponse(snapshots=[], count=0)

    try:
        from silkroute.db.repositories.budget_snapshots import get_snapshots

        rows = await get_snapshots(db_pool, project_id, start_date, end_date)
    except Exception:
        return BudgetSnapshotListResponse(snapshots=[], count=0)

    items = [
        BudgetSnapshotItem(
            project_id=str(row["project_id"]),
            snapshot_date=str(row["snapshot_date"]),
            total_cost_usd=float(row["total_cost_usd"]),
            total_requests=int(row["total_requests"]),
            total_tokens=int(row["total_tokens"]),
            free_requests=int(row["free_requests"]),
            free_cost_usd=float(row["free_cost_usd"]),
            standard_requests=int(row["standard_requests"]),
            standard_cost_usd=float(row["standard_cost_usd"]),
            premium_requests=int(row["premium_requests"]),
            premium_cost_usd=float(row["premium_cost_usd"]),
        )
        for row in rows
    ]
    return BudgetSnapshotListResponse(snapshots=items, count=len(items))


@router.get("/{project_id}")
async def project_budget(
    project_id: str,
    db_pool: asyncpg.Pool | None = Depends(get_db_pool),
) -> ProjectBudgetResponse:
    """Get per-project budget status.

    Fails open if Postgres is unavailable — returns zero spend values.
    """
    monthly_spent = 0.0
    daily_spent = 0.0
    monthly_limit: float | None = None

    if db_pool is not None:
        try:
            from silkroute.db.repositories.projects import (
                get_daily_spend,
                get_monthly_spend,
                get_project_budget,
            )

            monthly_spent = await get_monthly_spend(db_pool, project_id)
            daily_spent = await get_daily_spend(db_pool, project_id)
            monthly_limit = await get_project_budget(db_pool, project_id)
        except Exception:
            pass  # Fail open

    return ProjectBudgetResponse(
        project_id=project_id,
        monthly_spent_usd=monthly_spent,
        daily_spent_usd=daily_spent,
        monthly_limit_usd=monthly_limit,
    )
