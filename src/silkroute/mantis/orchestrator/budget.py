"""Budget tracking for orchestrated sub-agents.

BudgetTracker maintains a shared spend counter across concurrent sub-tasks.
allocate_budget() distributes the plan's total budget proportionally by tier.
"""

from __future__ import annotations

import asyncio
from dataclasses import dataclass, field

from silkroute.mantis.orchestrator.models import OrchestrationPlan


class BudgetExhaustedError(Exception):
    """Raised when the orchestration budget is fully spent."""


@dataclass
class BudgetTracker:
    """Thread-safe budget tracker for orchestrated sub-agents.

    Uses an asyncio.Lock to safely record concurrent spend from
    parallel sub-tasks within a stage.
    """

    total_usd: float = 10.0
    _spent_usd: float = 0.0
    _lock: asyncio.Lock = field(default_factory=asyncio.Lock)

    @property
    def remaining_usd(self) -> float:
        return max(0.0, self.total_usd - self._spent_usd)

    @property
    def spent_usd(self) -> float:
        return self._spent_usd

    async def record_spend(self, amount: float) -> None:
        """Record spend from a completed sub-task."""
        async with self._lock:
            self._spent_usd += amount

    async def try_reserve(self, amount: float) -> bool:
        """Try to reserve budget for a sub-task.

        Returns True if reservation succeeded, False if insufficient funds.
        """
        async with self._lock:
            if self._spent_usd + amount > self.total_usd:
                return False
            self._spent_usd += amount
            return True


# Tier weights for proportional budget allocation
_TIER_WEIGHTS = {
    "free": 0.5,
    "standard": 2.0,
    "premium": 5.0,
}

_CONTINGENCY_FRACTION = 0.10  # 10% held back
_FLOOR_USD = 0.01


def allocate_budget(plan: OrchestrationPlan) -> OrchestrationPlan:
    """Distribute the plan's total budget proportionally across sub-tasks.

    Budget is allocated by tier weight with a 10% contingency reserve
    and a $0.01 floor per sub-task. Modifies sub_tasks in place.
    """
    if not plan.sub_tasks:
        return plan

    available = plan.total_budget_usd * (1.0 - _CONTINGENCY_FRACTION)
    weights = [_TIER_WEIGHTS.get(st.tier_hint, 2.0) for st in plan.sub_tasks]
    total_weight = sum(weights)

    if total_weight == 0:
        total_weight = 1.0

    for st, w in zip(plan.sub_tasks, weights, strict=True):
        allocated = (w / total_weight) * available
        st.budget_usd = max(allocated, _FLOOR_USD)

    return plan
