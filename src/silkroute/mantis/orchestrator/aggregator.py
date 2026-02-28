"""Result aggregation — merge sub-agent results into a single AgentResult.

Combines outputs, sums costs and iterations, and determines overall
status based on sub-task outcomes.
"""

from __future__ import annotations

from silkroute.mantis.orchestrator.budget import BudgetTracker
from silkroute.mantis.orchestrator.models import (
    OrchestrationPlan,
    OrchestrationResult,
    SubAgentResult,
)


def aggregate_results(
    sub_results: list[SubAgentResult],
    plan: OrchestrationPlan,
    tracker: BudgetTracker,
) -> OrchestrationResult:
    """Aggregate sub-agent results into a single OrchestrationResult.

    Status logic:
    - All completed → "completed"
    - Any failed → "partial_failure"
    - All failed → "failed"
    """
    if not sub_results:
        return OrchestrationResult(
            status="completed",
            plan=plan,
            total_cost_usd=tracker.spent_usd,
        )

    total_cost = sum(sr.agent_result.cost_usd for sr in sub_results)
    total_iterations = sum(sr.agent_result.iterations for sr in sub_results)

    outputs = []
    for sr in sub_results:
        if sr.agent_result.output:
            outputs.append(sr.agent_result.output)

    merged = "\n\n---\n\n".join(outputs) if outputs else ""

    # Determine status
    statuses = [sr.agent_result.status for sr in sub_results]
    if all(s == "completed" for s in statuses):
        status = "completed"
    elif all(s in ("failed", "timeout", "budget_exceeded") for s in statuses):
        status = "failed"
    else:
        status = "partial_failure"

    return OrchestrationResult(
        status=status,
        sub_results=sub_results,
        total_cost_usd=total_cost,
        total_iterations=total_iterations,
        merged_output=merged,
        plan=plan,
    )
