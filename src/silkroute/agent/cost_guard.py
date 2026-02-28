"""Budget enforcement — per-session AND global (daily/monthly) caps.

Checks remaining budget before each ReAct iteration and returns
warning/critical thresholds based on BudgetConfig.

Global enforcement queries the PostgreSQL v_budget_remaining view.
Per-session enforcement uses in-memory session state (no DB needed).
Circuit breaker halts execution when hourly spend rate exceeds threshold.
"""

from __future__ import annotations

from dataclasses import dataclass

import structlog

from silkroute.agent.session import AgentSession
from silkroute.config.settings import BudgetConfig
from silkroute.providers.models import (
    ModelSpec,
    estimate_cost,
)

log = structlog.get_logger()

# Estimated tokens per iteration for budget projection
_EST_INPUT_TOKENS = 2000
_EST_OUTPUT_TOKENS = 1000

# Circuit breaker: halt if hourly spend exceeds this rate (USD)
CIRCUIT_BREAKER_HOURLY_USD = 2.0


@dataclass
class BudgetCheck:
    """Result of a pre-iteration budget check."""

    allowed: bool
    remaining_usd: float
    spent_usd: float
    limit_usd: float
    warning: str = ""


@dataclass
class GlobalBudgetCheck:
    """Result of a global (daily/monthly) budget check."""

    allowed: bool
    daily_spent_usd: float
    daily_limit_usd: float
    monthly_spent_usd: float
    monthly_limit_usd: float
    hourly_rate_usd: float
    warning: str = ""


def check_budget(
    session: AgentSession,
    model: ModelSpec,
    budget_config: BudgetConfig,
) -> BudgetCheck:
    """Check if the session has enough budget for another iteration.

    Uses the session's budget_limit_usd as the per-session cap.
    Estimates the cost of one more iteration to decide if we can proceed.
    """
    spent = session.total_cost_usd
    limit = session.budget_limit_usd
    remaining = limit - spent

    # Estimate cost of next iteration
    next_cost = estimate_cost(model, _EST_INPUT_TOKENS, _EST_OUTPUT_TOKENS)

    # Check if we'd exceed the session budget
    if remaining < next_cost:
        return BudgetCheck(
            allowed=False,
            remaining_usd=remaining,
            spent_usd=spent,
            limit_usd=limit,
            warning=f"Budget exhausted: ${spent:.4f} spent of ${limit:.2f} limit",
        )

    # Check warning thresholds (as fraction of session budget)
    usage_fraction = spent / limit if limit > 0 else 0.0
    warning = ""

    if usage_fraction >= budget_config.alert_threshold_critical:
        warning = (
            f"CRITICAL: {usage_fraction:.0%} of session budget used"
            f" (${spent:.4f} / ${limit:.2f})"
        )
    elif usage_fraction >= budget_config.alert_threshold_warning:
        warning = (
            f"WARNING: {usage_fraction:.0%} of session budget used"
            f" (${spent:.4f} / ${limit:.2f})"
        )

    return BudgetCheck(
        allowed=True,
        remaining_usd=remaining,
        spent_usd=spent,
        limit_usd=limit,
        warning=warning,
    )


def check_global_budget(
    *,
    daily_spent: float,
    monthly_spent: float,
    hourly_rate: float,
    budget_config: BudgetConfig,
) -> GlobalBudgetCheck:
    """Check global budget limits (daily, monthly) and circuit breaker.

    This is a pure function — callers are responsible for querying the DB
    to get daily_spent, monthly_spent, and hourly_rate values.

    Enforcement order:
    1. Circuit breaker (hourly rate > $2/hr) — immediate halt
    2. Monthly cap exceeded — halt
    3. Daily cap exceeded — halt
    4. Warning thresholds — allow with warning
    """
    daily_limit = budget_config.daily_max_usd
    monthly_limit = budget_config.monthly_max_usd

    # Circuit breaker: runaway spend detection
    if hourly_rate > CIRCUIT_BREAKER_HOURLY_USD:
        log.warning(
            "circuit_breaker_tripped",
            hourly_rate=hourly_rate,
            threshold=CIRCUIT_BREAKER_HOURLY_USD,
        )
        return GlobalBudgetCheck(
            allowed=False,
            daily_spent_usd=daily_spent,
            daily_limit_usd=daily_limit,
            monthly_spent_usd=monthly_spent,
            monthly_limit_usd=monthly_limit,
            hourly_rate_usd=hourly_rate,
            warning=(
                f"CIRCUIT BREAKER: Hourly spend rate ${hourly_rate:.2f}/hr "
                f"exceeds ${CIRCUIT_BREAKER_HOURLY_USD:.2f}/hr threshold"
            ),
        )

    # Monthly cap
    if monthly_spent >= monthly_limit:
        return GlobalBudgetCheck(
            allowed=False,
            daily_spent_usd=daily_spent,
            daily_limit_usd=daily_limit,
            monthly_spent_usd=monthly_spent,
            monthly_limit_usd=monthly_limit,
            hourly_rate_usd=hourly_rate,
            warning=(
                f"Monthly budget exceeded: ${monthly_spent:.2f} / ${monthly_limit:.2f}"
            ),
        )

    # Daily cap
    if daily_spent >= daily_limit:
        return GlobalBudgetCheck(
            allowed=False,
            daily_spent_usd=daily_spent,
            daily_limit_usd=daily_limit,
            monthly_spent_usd=monthly_spent,
            monthly_limit_usd=monthly_limit,
            hourly_rate_usd=hourly_rate,
            warning=(
                f"Daily budget exceeded: ${daily_spent:.2f} / ${daily_limit:.2f}"
            ),
        )

    # Warning thresholds on monthly budget
    monthly_fraction = monthly_spent / monthly_limit if monthly_limit > 0 else 0.0
    warning = ""

    if monthly_fraction >= budget_config.alert_threshold_critical:
        warning = (
            f"CRITICAL: {monthly_fraction:.0%} of monthly budget used"
            f" (${monthly_spent:.2f} / ${monthly_limit:.2f})"
        )
    elif monthly_fraction >= budget_config.alert_threshold_warning:
        warning = (
            f"WARNING: {monthly_fraction:.0%} of monthly budget used"
            f" (${monthly_spent:.2f} / ${monthly_limit:.2f})"
        )

    return GlobalBudgetCheck(
        allowed=True,
        daily_spent_usd=daily_spent,
        daily_limit_usd=daily_limit,
        monthly_spent_usd=monthly_spent,
        monthly_limit_usd=monthly_limit,
        hourly_rate_usd=hourly_rate,
        warning=warning,
    )
