"""Pydantic v2 request/response schemas for the SilkRoute REST API."""

from __future__ import annotations

from pydantic import BaseModel, Field

# --- Task endpoints ---


class TaskSubmitRequest(BaseModel):
    """POST /tasks request body."""

    task: str = Field(..., min_length=1, description="Task description for the agent")
    project_id: str = Field(default="default", description="Project for cost attribution")
    model_override: str | None = Field(default=None, description="Override model selection")
    tier_override: str | None = Field(default=None, description="Override routing tier")
    max_iterations: int = Field(default=25, ge=1, le=200)
    budget_limit_usd: float = Field(default=10.0, ge=0.01, le=100.0)


class TaskSubmitResponse(BaseModel):
    """POST /tasks response."""

    id: str
    status: str = "queued"


class TaskResultResponse(BaseModel):
    """GET /tasks/{task_id}/result response."""

    request_id: str
    status: str
    session_id: str = ""
    cost_usd: float = 0.0
    iterations: int = 0
    duration_ms: int = 0
    error: str | None = None


class QueueStatusResponse(BaseModel):
    """GET /tasks/queue/status response."""

    pending: int
    total_submitted: int
    total_completed: int


# --- Runtime endpoints ---


class RuntimeInvokeRequest(BaseModel):
    """POST /runtime/invoke request body."""

    task: str = Field(..., min_length=1)
    runtime_type: str | None = Field(default=None, description="legacy | deepagents")
    model_override: str | None = None
    max_iterations: int = Field(default=25, ge=1, le=200)
    budget_limit_usd: float = Field(default=10.0, ge=0.01, le=100.0)
    orchestrate: bool = Field(
        default=False,
        description="Route to OrchestratorRuntime for task decomposition",
    )


class RuntimeInvokeResponse(BaseModel):
    """POST /runtime/invoke response."""

    status: str
    session_id: str = ""
    output: str = ""
    iterations: int = 0
    cost_usd: float = 0.0
    error: str = ""


# --- Model catalog ---


class ModelResponse(BaseModel):
    """Single model in the catalog."""

    model_id: str
    name: str
    provider: str
    tier: str
    input_cost_per_m: float
    output_cost_per_m: float
    context_window: int
    max_output_tokens: int
    capabilities: list[str]
    supports_tool_calling: bool
    supports_streaming: bool
    is_moe: bool
    is_free: bool


# --- Budget ---


class GlobalBudgetResponse(BaseModel):
    """GET /budget response."""

    daily_spent_usd: float
    daily_limit_usd: float
    monthly_spent_usd: float
    monthly_limit_usd: float
    hourly_rate_usd: float
    allowed: bool
    warning: str = ""


class ProjectBudgetResponse(BaseModel):
    """GET /budget/{project_id} response."""

    project_id: str
    monthly_spent_usd: float
    daily_spent_usd: float
    monthly_limit_usd: float | None = None


# --- Supervisor endpoints ---


class SupervisorStepRequest(BaseModel):
    """A step in a supervisor session create request."""

    name: str = Field(..., min_length=1)
    description: str = Field(default="", description="Task description for the step")
    depends_on: list[str] = Field(default_factory=list)
    runtime_type: str = Field(default="orchestrator")
    max_retries: int = Field(default=2, ge=0, le=10)
    condition: str | None = Field(default=None, description="Condition expression")


class SupervisorSessionCreateRequest(BaseModel):
    """POST /supervisor/sessions request body."""

    description: str = Field(..., min_length=1)
    project_id: str = Field(default="default")
    steps: list[SupervisorStepRequest] = Field(..., min_length=1)
    total_budget_usd: float = Field(default=10.0, ge=0.01, le=100.0)
    timeout_seconds: int = Field(default=3600, ge=60, le=86400)


class SupervisorStepResponse(BaseModel):
    """A step in a supervisor session response."""

    id: str
    name: str
    status: str
    cost_usd: float = 0.0
    output: str = ""
    error: str = ""
    retry_count: int = 0


class SupervisorSessionResponse(BaseModel):
    """Supervisor session response."""

    id: str
    project_id: str
    status: str
    total_cost_usd: float = 0.0
    steps: list[SupervisorStepResponse] = Field(default_factory=list)
    created_at: str = ""
    updated_at: str = ""
    error: str = ""


# --- Skills endpoints ---


class SkillResponse(BaseModel):
    """Single skill in the catalog."""

    name: str
    description: str
    category: str
    parameters: dict = Field(default_factory=dict)
    is_llm_native: bool = False
    model_hint: str = ""
    max_budget_usd: float = 0.50
    version: str = "0.1.0"
    required_tools: list[str] = Field(default_factory=list)


# --- Context7 endpoints ---


class Context7ResolveRequest(BaseModel):
    """POST /context7/resolve request body."""

    library_name: str = Field(..., min_length=1, description="Library name to resolve")
    query: str = Field(default="", description="Optional query to filter results")


class Context7ResolveResponse(BaseModel):
    """POST /context7/resolve response."""

    found: bool
    library_id: str = ""
    library_name: str = ""
    version: str = ""
    trust_score: float = 0.0


class Context7QueryRequest(BaseModel):
    """POST /context7/query request body."""

    library_name: str = Field(..., min_length=1)
    query: str = Field(..., min_length=1)


class Context7QueryResponse(BaseModel):
    """POST /context7/query response."""

    library_name: str
    snippets: list[dict] = Field(default_factory=list)
    truncated: bool = False
    error: str = ""
