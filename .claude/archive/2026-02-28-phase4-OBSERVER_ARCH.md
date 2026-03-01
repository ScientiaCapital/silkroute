# SilkRoute: Architecture Observer Report
**Date:** 2026-02-28
**Session:** Phase 4 — Supervisor + Ralph Mode
**Status:** COMPLETE

---

## Architecture Assessment

### New Components

```
mantis/supervisor/
  models.py    — Data models (SessionStatus, StepStatus, SupervisorStep/Plan/Checkpoint/Session)
  runtime.py   — SupervisorRuntime implementing AgentRuntime Protocol
  ralph.py     — RalphController autonomous scheduling loop
  __init__.py  — Package exports

db/repositories/supervisor.py — CRUD for supervisor_sessions table
api/routes/supervisor.py      — REST endpoints for supervisor sessions
```

### Design Patterns

1. **Protocol conformance**: SupervisorRuntime implements AgentRuntime Protocol — pluggable via registry
2. **Sequential + conditional steps**: SupervisorPlan manages sequential execution with depends_on, while OrchestrationPlan manages parallel DAG stages. Different coordination patterns for different needs.
3. **Inter-step context via dict**: `plan.context[step_id]` — serializable to JSONB, simple key-value avoids complex message-passing
4. **Reserve-then-settle budget**: Atomic budget claims prevent over-spending in concurrent scenarios
5. **Fire-and-forget checkpointing**: Follows existing `agent/loop.py` pattern for non-blocking persistence
6. **Safe condition evaluation**: Structured expression parser — no arbitrary code execution

### Drift Detection

| Pattern | Expected | Actual | Status |
|---------|----------|--------|--------|
| AgentRuntime Protocol | invoke/stream/name | Implemented | OK |
| Pool-based DB functions | Async functions with pool param | Followed | OK |
| Middleware Protocol | before/after hooks | 3 new middleware follow pattern | OK |
| Config pattern | Pydantic BaseSettings with env_prefix | SupervisorConfig follows | OK |
| API auth | require_auth dependency | All supervisor routes protected | OK |
| Error handling | Specific exception types | Narrowed in orchestrator, broad in ralph (acceptable) | OK |

### Architectural Risks

1. **Ralph Mode autonomy boundary**: RalphController consumes up to 3 tasks per cycle — no human approval gate. Mitigated by budget gate and configurable cron schedule.
2. **Supervisor-Orchestrator coupling**: SupervisorRuntime creates OrchestratorRuntime children via registry. Coupling is loose (factory pattern) but forms a 2-level hierarchy.

### Recommendations for Phase 5
- LLM-based plan generation to replace keyword splitting in _build_plan_from_task
- Dashboard UI for supervisor session monitoring
- WebSocket live updates for long-running supervisor sessions
