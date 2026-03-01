"""Agent runtime protocol — the contract all runtime backends must satisfy.

Uses Python's Protocol for structural typing: any class that implements
create(), invoke(), and stream() is a valid AgentRuntime, without
needing explicit inheritance. This is essential for wrapping third-party
libraries that we can't modify.
"""

from __future__ import annotations

import os
from collections.abc import AsyncIterator
from dataclasses import dataclass, field
from typing import Any, Protocol, runtime_checkable


class RuntimeType:
    """Known runtime backend identifiers."""

    LEGACY = "legacy"
    DEEP_AGENTS = "deepagents"
    ORCHESTRATOR = "orchestrator"
    SUPERVISOR = "supervisor"


@dataclass
class RuntimeConfig:
    """Configuration for an agent runtime instance."""

    runtime_type: str = field(
        default_factory=lambda: os.environ.get("SILKROUTE_RUNTIME", RuntimeType.LEGACY)
    )
    workspace_dir: str = "."
    project_id: str = "default"
    model_override: str | None = None
    tier_override: str | None = None
    max_iterations: int = 25
    budget_limit_usd: float = 10.0
    extra: dict[str, Any] = field(default_factory=dict)


@dataclass
class AgentResult:
    """Unified result from any runtime backend."""

    status: str  # "completed", "failed", "timeout", "budget_exceeded"
    session_id: str = ""
    iterations: int = 0
    cost_usd: float = 0.0
    output: str = ""
    error: str = ""
    metadata: dict[str, Any] = field(default_factory=dict)

    @property
    def success(self) -> bool:
        return self.status == "completed"


@runtime_checkable
class AgentRuntime(Protocol):
    """Protocol for agent runtime backends.

    Implementations:
    - LegacyRuntime: wraps existing run_agent() ReAct loop
    - DeepAgentsRuntime: wraps create_deep_agent() (Phase 1)
    """

    async def invoke(self, task: str, config: RuntimeConfig | None = None) -> AgentResult:
        """Run a task to completion and return the result."""
        ...

    async def stream(self, task: str, config: RuntimeConfig | None = None) -> AsyncIterator[str]:
        """Stream incremental output from a task execution.

        Yields text chunks as the agent works.
        Default: not all runtimes support streaming.
        """
        ...

    @property
    def name(self) -> str:
        """Human-readable name of this runtime."""
        ...
