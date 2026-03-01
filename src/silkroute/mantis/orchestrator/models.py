"""Data models for multi-agent orchestration.

SubTask, OrchestrationPlan, SubAgentResult, and OrchestrationResult form
the core data layer. OrchestrationPlan.stages uses Kahn's algorithm
for topological sorting — sub-tasks are grouped into stages that can
execute in parallel within each stage but sequentially between stages.
"""

from __future__ import annotations

import uuid
from collections import defaultdict, deque
from dataclasses import dataclass, field
from typing import Any

from silkroute.mantis.runtime.interface import AgentResult, RuntimeType


@dataclass
class RetryConfig:
    """Retry configuration for sub-task execution."""

    max_retries: int = 3
    backoff_base: float = 1.0
    backoff_factor: float = 2.0
    retryable_statuses: frozenset[str] = field(
        default_factory=lambda: frozenset({"failed", "timeout"})
    )


@dataclass
class SubTask:
    """A single unit of work delegated to a child runtime."""

    id: str = field(default_factory=lambda: uuid.uuid4().hex[:8])
    parent_task: str = ""
    description: str = ""
    runtime_type: str = RuntimeType.LEGACY
    tier_hint: str = "standard"
    depends_on: list[str] = field(default_factory=list)
    budget_usd: float = 1.0
    max_iterations: int = 25
    priority: int = 0
    metadata: dict[str, Any] = field(default_factory=dict)


@dataclass
class OrchestrationPlan:
    """A plan for executing multiple sub-tasks with dependency ordering.

    The ``stages`` property groups sub-tasks into topologically-sorted
    stages using Kahn's algorithm. Tasks within a stage have no
    inter-dependencies and can run in parallel.
    """

    parent_task: str = ""
    sub_tasks: list[SubTask] = field(default_factory=list)
    strategy: str = "parallel_stages"
    total_budget_usd: float = 10.0
    metadata: dict[str, Any] = field(default_factory=dict)

    @property
    def stages(self) -> list[list[SubTask]]:
        """Group sub-tasks into parallel-safe execution stages.

        Uses Kahn's algorithm for topological sort. Tasks in the same
        stage have all dependencies satisfied by earlier stages.

        Raises:
            ValueError: If the dependency graph contains a cycle.
        """
        if not self.sub_tasks:
            return []

        task_map = {t.id: t for t in self.sub_tasks}
        valid_ids = set(task_map.keys())

        # Build adjacency and in-degree maps
        in_degree: dict[str, int] = defaultdict(int)
        dependents: dict[str, list[str]] = defaultdict(list)

        for t in self.sub_tasks:
            in_degree.setdefault(t.id, 0)
            for dep in t.depends_on:
                if dep in valid_ids:
                    in_degree[t.id] += 1
                    dependents[dep].append(t.id)

        # BFS by stages (wave-based Kahn's)
        result_stages: list[list[SubTask]] = []
        queue: deque[str] = deque(
            tid for tid, deg in in_degree.items() if deg == 0
        )

        processed = 0
        while queue:
            stage_ids: list[str] = []
            for _ in range(len(queue)):
                tid = queue.popleft()
                stage_ids.append(tid)
                processed += 1

            # Sort by priority (higher first) for deterministic ordering
            stage_ids.sort(key=lambda tid: (-task_map[tid].priority, tid))
            result_stages.append([task_map[tid] for tid in stage_ids])

            for tid in stage_ids:
                for dep_id in dependents[tid]:
                    in_degree[dep_id] -= 1
                    if in_degree[dep_id] == 0:
                        queue.append(dep_id)

        if processed != len(self.sub_tasks):
            raise ValueError(
                "Dependency cycle detected in orchestration plan. "
                f"Processed {processed}/{len(self.sub_tasks)} tasks."
            )

        return result_stages


@dataclass
class SubAgentResult:
    """Result from a single sub-agent execution."""

    sub_task_id: str = ""
    agent_result: AgentResult = field(default_factory=lambda: AgentResult(status="pending"))
    runtime_used: str = RuntimeType.LEGACY
    stage: int = 0
    elapsed_ms: int = 0


@dataclass
class OrchestrationResult:
    """Aggregated result from all sub-agents."""

    status: str = "completed"
    sub_results: list[SubAgentResult] = field(default_factory=list)
    total_cost_usd: float = 0.0
    total_iterations: int = 0
    merged_output: str = ""
    plan: OrchestrationPlan | None = None
