"""In-memory agent session state.

Tracks iterations, tool calls, token usage, and cost for a single agent run.
No database dependency — persistence comes in Phase 3.
"""

from __future__ import annotations

import uuid
from dataclasses import dataclass, field
from datetime import UTC, datetime
from enum import StrEnum
from typing import Any


class SessionStatus(StrEnum):
    """Agent session lifecycle states."""

    ACTIVE = "active"
    COMPLETED = "completed"
    FAILED = "failed"
    TIMEOUT = "timeout"
    BUDGET_EXCEEDED = "budget_exceeded"


@dataclass
class ToolCall:
    """Record of a single tool invocation within an iteration."""

    tool_name: str
    tool_input: dict[str, Any]
    tool_output: str = ""
    success: bool = True
    error_message: str = ""
    duration_ms: int = 0


@dataclass
class Iteration:
    """A single Think → Act → Observe cycle."""

    number: int
    thought: str = ""
    tool_calls: list[ToolCall] = field(default_factory=list)
    cost_usd: float = 0.0
    input_tokens: int = 0
    output_tokens: int = 0
    latency_ms: int = 0


@dataclass
class AgentSession:
    """Full state for one agent run."""

    task: str
    model_id: str
    id: str = field(default_factory=lambda: str(uuid.uuid4()))
    project_id: str = "default"
    status: SessionStatus = SessionStatus.ACTIVE
    iterations: list[Iteration] = field(default_factory=list)
    messages: list[dict[str, Any]] = field(default_factory=list)
    budget_limit_usd: float = 10.0
    started_at: datetime = field(default_factory=lambda: datetime.now(UTC))
    completed_at: datetime | None = None

    @property
    def iteration_count(self) -> int:
        return len(self.iterations)

    @property
    def total_cost_usd(self) -> float:
        return sum(it.cost_usd for it in self.iterations)

    @property
    def total_input_tokens(self) -> int:
        return sum(it.input_tokens for it in self.iterations)

    @property
    def total_output_tokens(self) -> int:
        return sum(it.output_tokens for it in self.iterations)

    def add_iteration(self, iteration: Iteration) -> None:
        """Append a completed iteration to the session."""
        self.iterations.append(iteration)

    def complete(self, status: SessionStatus) -> None:
        """Mark session as finished with the given terminal status."""
        self.status = status
        self.completed_at = datetime.now(UTC)
