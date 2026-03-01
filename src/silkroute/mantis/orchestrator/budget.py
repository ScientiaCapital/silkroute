"""Budget tracking for orchestrated sub-agents.

BudgetTracker maintains a shared spend counter across concurrent sub-tasks.
allocate_budget() distributes the plan's total budget proportionally by tier.
"""

from __future__ import annotations

import asyncio
import copy
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

    async def settle(self, reserved: float, actual: float) -> None:
        """Settle a reservation: release the difference between reserved and actual.

        Called after a sub-task completes to adjust for over-reservation.
        """
        async with self._lock:
            self._spent_usd -= (reserved - actual)


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
    and a $0.01 floor per sub-task. Returns a deep copy — the original
    plan is never mutated.
    """
    if not plan.sub_tasks:
        return plan

    result = copy.deepcopy(plan)

    available = result.total_budget_usd * (1.0 - _CONTINGENCY_FRACTION)
    weights = [_TIER_WEIGHTS.get(st.tier_hint, 2.0) for st in result.sub_tasks]
    total_weight = sum(weights)

    if total_weight == 0:
        total_weight = 1.0

    for st, w in zip(result.sub_tasks, weights, strict=True):
        allocated = (w / total_weight) * available
        st.budget_usd = max(allocated, _FLOOR_USD)

    return result
