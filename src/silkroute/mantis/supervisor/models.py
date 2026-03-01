"""Data models for supervisor workflows.

SupervisorStep, SupervisorPlan, SupervisorCheckpoint, and SupervisorSession
form the core data layer for long-running compound workflows. Steps execute
sequentially with dependency tracking and conditional evaluation.
"""

from __future__ import annotations

import uuid
from dataclasses import dataclass, field
from datetime import UTC, datetime
from enum import StrEnum
from typing import Any


class SessionStatus(StrEnum):
    """Supervisor session lifecycle states."""

    PENDING = "pending"
    RUNNING = "running"
    PAUSED = "paused"
    COMPLETED = "completed"
    FAILED = "failed"
    CANCELLED = "cancelled"


class StepStatus(StrEnum):
    """Individual step execution states."""

    PENDING = "pending"
    RUNNING = "running"
    COMPLETED = "completed"
    FAILED = "failed"
    SKIPPED = "skipped"


@dataclass
class SupervisorStep:
    """A single step in a supervisor workflow."""

    id: str = field(default_factory=lambda: uuid.uuid4().hex[:8])
    name: str = ""
    description: str = ""
    status: StepStatus = StepStatus.PENDING
    depends_on: list[str] = field(default_factory=list)
    runtime_type: str = "orchestrator"
    config: dict[str, Any] | None = None
    max_retries: int = 2
    retry_count: int = 0
    retry_backoff_seconds: float = 5.0
    condition: str | None = None
    skip_on_failure: bool = False
    result: dict[str, Any] | None = None
    output: str = ""
    cost_usd: float = 0.0
    started_at: datetime | None = None
    completed_at: datetime | None = None
    error: str = ""
    metadata: dict[str, Any] = field(default_factory=dict)


@dataclass
class SupervisorPlan:
    """Execution plan for a supervisor workflow.

    Steps execute sequentially via next_pending_step(), respecting
    depends_on constraints and condition evaluation.
    """

    id: str = field(default_factory=lambda: uuid.uuid4().hex[:12])
    project_id: str = "default"
    description: str = ""
    steps: list[SupervisorStep] = field(default_factory=list)
    total_budget_usd: float = 10.0
    timeout_seconds: int = 3600
    context: dict[str, Any] = field(default_factory=dict)

    def next_pending_step(self) -> SupervisorStep | None:
        """Return the next step whose dependencies are all satisfied.

        A step is ready when:
        - Its status is PENDING
        - All depends_on steps are in a terminal state (completed/failed/skipped)
        """
        completed_ids = {
            s.id
            for s in self.steps
            if s.status in (StepStatus.COMPLETED, StepStatus.FAILED, StepStatus.SKIPPED)
        }
        for step in self.steps:
            if step.status != StepStatus.PENDING:
                continue
            if all(dep in completed_ids for dep in step.depends_on):
                return step
        return None

    @property
    def is_complete(self) -> bool:
        """True when all steps are in a terminal state."""
        terminal = {StepStatus.COMPLETED, StepStatus.FAILED, StepStatus.SKIPPED}
        return all(s.status in terminal for s in self.steps) if self.steps else True

    @property
    def overall_status(self) -> SessionStatus:
        """Derive session status from step states."""
        if not self.steps:
            return SessionStatus.COMPLETED

        statuses = {s.status for s in self.steps}

        if statuses == {StepStatus.PENDING}:
            return SessionStatus.PENDING

        if any(s == StepStatus.RUNNING for s in statuses):
            return SessionStatus.RUNNING

        if not self.is_complete:
            return SessionStatus.RUNNING

        # All terminal — check for failures
        if all(s.status == StepStatus.COMPLETED for s in self.steps):
            return SessionStatus.COMPLETED

        if all(s.status in (StepStatus.FAILED, StepStatus.SKIPPED) for s in self.steps):
            return SessionStatus.FAILED

        # Mix of completed/failed/skipped
        return SessionStatus.COMPLETED

    def to_dict(self) -> dict[str, Any]:
        """Serialize plan for JSONB storage."""
        return {
            "id": self.id,
            "project_id": self.project_id,
            "description": self.description,
            "total_budget_usd": self.total_budget_usd,
            "timeout_seconds": self.timeout_seconds,
            "steps": [
                {
                    "id": s.id,
                    "name": s.name,
                    "description": s.description,
                    "status": s.status.value,
                    "depends_on": s.depends_on,
                    "runtime_type": s.runtime_type,
                    "config": s.config,
                    "max_retries": s.max_retries,
                    "retry_count": s.retry_count,
                    "retry_backoff_seconds": s.retry_backoff_seconds,
                    "condition": s.condition,
                    "skip_on_failure": s.skip_on_failure,
                    "output": s.output,
                    "cost_usd": s.cost_usd,
                    "error": s.error,
                    "metadata": s.metadata,
                }
                for s in self.steps
            ],
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> SupervisorPlan:
        """Deserialize plan from JSONB."""
        steps = [
            SupervisorStep(
                id=s["id"],
                name=s.get("name", ""),
                description=s.get("description", ""),
                status=StepStatus(s.get("status", "pending")),
                depends_on=s.get("depends_on", []),
                runtime_type=s.get("runtime_type", "orchestrator"),
                config=s.get("config"),
                max_retries=s.get("max_retries", 2),
                retry_count=s.get("retry_count", 0),
                retry_backoff_seconds=s.get("retry_backoff_seconds", 5.0),
                condition=s.get("condition"),
                skip_on_failure=s.get("skip_on_failure", False),
                output=s.get("output", ""),
                cost_usd=s.get("cost_usd", 0.0),
                error=s.get("error", ""),
                metadata=s.get("metadata", {}),
            )
            for s in data.get("steps", [])
        ]
        return cls(
            id=data.get("id", uuid.uuid4().hex[:12]),
            project_id=data.get("project_id", "default"),
            description=data.get("description", ""),
            steps=steps,
            total_budget_usd=data.get("total_budget_usd", 10.0),
            timeout_seconds=data.get("timeout_seconds", 3600),
        )


@dataclass
class SupervisorCheckpoint:
    """Snapshot of supervisor state for persistence and resume."""

    session_id: str = ""
    plan_json: dict[str, Any] = field(default_factory=dict)
    context_json: dict[str, Any] = field(default_factory=dict)
    step_results: dict[str, Any] = field(default_factory=dict)
    total_cost_usd: float = 0.0
    created_at: datetime = field(default_factory=lambda: datetime.now(UTC))


@dataclass
class SupervisorSession:
    """A supervisor workflow execution instance."""

    id: str = field(default_factory=lambda: uuid.uuid4().hex[:16])
    project_id: str = "default"
    status: SessionStatus = SessionStatus.PENDING
    plan: SupervisorPlan = field(default_factory=SupervisorPlan)
    checkpoint: SupervisorCheckpoint | None = None
    total_cost_usd: float = 0.0
    config_json: dict[str, Any] = field(default_factory=dict)
    created_at: datetime = field(default_factory=lambda: datetime.now(UTC))
    updated_at: datetime = field(default_factory=lambda: datetime.now(UTC))
    error: str = ""
