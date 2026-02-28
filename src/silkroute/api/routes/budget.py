"""Budget endpoints — global and per-project budget status.

GET /budget              → Global daily/monthly budget status
GET /budget/{project_id} → Per-project spend and limits

Fails open if Postgres is unavailable (returns zeros rather than 503).
"""

from __future__ import annotations

from typing import TYPE_CHECKING

from fastapi import APIRouter, Depends

from silkroute.api.auth import require_auth
from silkroute.api.deps import get_budget_config, get_db_pool
from silkroute.api.models import GlobalBudgetResponse, ProjectBudgetResponse
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
