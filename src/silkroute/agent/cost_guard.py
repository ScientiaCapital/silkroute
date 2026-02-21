"""Per-session budget enforcement.

Checks remaining budget before each ReAct iteration and returns
warning/critical thresholds based on BudgetConfig.
"""

from __future__ import annotations

from dataclasses import dataclass

from silkroute.agent.session import AgentSession
from silkroute.config.settings import BudgetConfig
from silkroute.providers.models import (
    ModelSpec,
    estimate_cost,
)

# Estimated tokens per iteration for budget projection
_EST_INPUT_TOKENS = 2000
_EST_OUTPUT_TOKENS = 1000


@dataclass
class BudgetCheck:
    """Result of a pre-iteration budget check."""

    allowed: bool
    remaining_usd: float
    spent_usd: float
    limit_usd: float
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
