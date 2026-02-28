"""Multi-agent orchestration — decompose, delegate, aggregate.

The orchestrator splits compound tasks into sub-tasks, routes each to
the appropriate runtime (Legacy or DeepAgents), and aggregates results.

Key components:
- models: Data classes for sub-tasks, plans, and results
- decomposer: Keyword-based task decomposition (no LLM calls)
- middleware: Budget, logging, and validation middleware chain
- budget: Shared budget tracking across sub-agents
- aggregator: Merge sub-agent results into a single AgentResult
- runtime: OrchestratorRuntime implementing the AgentRuntime Protocol
"""

from silkroute.mantis.orchestrator.aggregator import aggregate_results
from silkroute.mantis.orchestrator.budget import (
    BudgetExhaustedError,
    BudgetTracker,
    allocate_budget,
)
from silkroute.mantis.orchestrator.decomposer import (
    KeywordDecomposer,
    SingleTaskDecomposer,
    TaskDecomposer,
)
from silkroute.mantis.orchestrator.models import (
    OrchestrationPlan,
    OrchestrationResult,
    SubAgentResult,
    SubTask,
)

__all__ = [
    "BudgetExhaustedError",
    "BudgetTracker",
    "KeywordDecomposer",
    "OrchestrationPlan",
    "OrchestrationResult",
    "SingleTaskDecomposer",
    "SubAgentResult",
    "SubTask",
    "TaskDecomposer",
    "aggregate_results",
    "allocate_budget",
]
