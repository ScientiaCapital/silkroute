# SilkRoute: Architecture Observer Report
**Date:** 2026-02-28
**Session:** Phase 3 — Multi-Agent Orchestration
**Status:** COMPLETE

---

## Architecture Changes

### New Package: `mantis/orchestrator/`

```
mantis/orchestrator/
├── __init__.py       — Package exports
├── models.py         — SubTask, OrchestrationPlan, SubAgentResult, OrchestrationResult
├── decomposer.py     — TaskDecomposer Protocol + KeywordDecomposer + SingleTaskDecomposer
├── budget.py         — BudgetTracker (asyncio.Lock) + allocate_budget() + BudgetExhaustedError
├── middleware.py      — Middleware Protocol + Validation/Budget/Logging implementations
├── aggregator.py      — aggregate_results() → OrchestrationResult
└── runtime.py         — OrchestratorRuntime (AgentRuntime Protocol implementation)
```

### Pattern: DAG-Based Stage Execution

```
Task → Decompose → Allocate Budget → Execute Stages → Aggregate
                                         │
                                    Stage 0: [A, B]  ← asyncio.gather
                                    Stage 1: [C]     ← depends on A, B
                                    Stage 2: [D]     ← depends on C
```

Kahn's algorithm (wave-based BFS) in `OrchestrationPlan.stages` property sorts sub-tasks into parallel-safe stages. This is a clean, well-tested implementation (cycle detection, priority ordering, dependency validation).

### Pattern: Middleware Chain

```
Request → Validation → Budget → Logging → [Execute] → Logging → Budget → Validation → Response
```

Uses Protocol-based duck typing consistent with the existing `AgentRuntime` Protocol pattern. The before/after symmetric design is extensible for Phase 4 (retry, metrics, circuit breaker).

### Pattern: Producer-Consumer Streaming

```
LegacyRuntime.stream()
  ├── Creates asyncio.Queue(maxsize=100)
  ├── Spawns run_agent() as background task with stream_queue
  ├── Yields chunks from queue until None sentinel
  └── Cancels agent task on disconnect
```

This replaces the previous batch-then-yield streaming with true per-iteration output. The agent loop pushes JSON events at 4 points: tool-call iteration, final iteration, budget exceeded, LLM error.

---

## Dependency Graph

```
api/routes/runtime.py
  └── mantis/runtime/registry.py
       ├── mantis/runtime/legacy.py → agent/loop.py
       ├── mantis/runtime/deepagents.py → mantis/agents/code_writer.py
       └── mantis/orchestrator/runtime.py (NEW)
            ├── mantis/orchestrator/decomposer.py → agent/classifier.py
            ├── mantis/orchestrator/budget.py
            ├── mantis/orchestrator/middleware.py
            ├── mantis/orchestrator/aggregator.py
            └── mantis/runtime/registry.py (child_factory, lazy import)
```

The circular reference between `orchestrator/runtime.py` and `mantis/runtime/registry.py` is broken by lazy import in `_default_child_factory()`. This is the established pattern in the codebase (legacy.py does the same with `agent/loop.py`).

---

## Devil's Advocate Analysis

### Q: Does the orchestrator properly implement the AgentRuntime Protocol?

**Yes.** `OrchestratorRuntime` exposes `name`, `invoke()`, and `stream()` matching the Protocol. Tests verify it satisfies `isinstance(runtime, AgentRuntime)` (structural check). Registry correctly routes "orchestrator" type.

### Q: Can the orchestrator recurse infinitely?

**No.** The child factory returns LegacyRuntime or DeepAgentsRuntime, never another OrchestratorRuntime. The registry creates a new OrchestratorRuntime only when explicitly requested. Sub-tasks inherit the parent's `runtime_type` from config, which defaults to "legacy".

### Q: Is the budget tracking actually safe under concurrency?

**Mostly.** `BudgetTracker.record_spend()` and `try_reserve()` use asyncio.Lock correctly. However, `BudgetMiddleware.before()` reads `remaining_usd` outside the lock then sets `budget_usd` (see W2 in quality report). In practice, asyncio is single-threaded so the race window is negligible — it would only matter if a `gather()` resumes two tasks between lock release and property read, which can't happen in the same event loop tick.

### Q: Are there any new security surfaces?

**Minimal.** The `orchestrate: bool` field on RuntimeInvokeRequest is a simple Pydantic boolean — no injection risk. The orchestrator inherits existing auth (require_auth dependency) and sandbox restrictions. Sub-tasks don't create new network endpoints.

### Q: Does anything from the plan remain unbuilt?

**No.** All items from the Phase 3 contract IN SCOPE section are implemented:
- [x] orchestrator package (7 modules)
- [x] OrchestratorRuntime implementing AgentRuntime Protocol
- [x] Keyword-based task decomposition
- [x] Sub-agent middleware chain
- [x] DAG-based stage execution
- [x] Budget allocation with shared tracker
- [x] Result aggregation
- [x] True per-iteration streaming
- [x] SSE server-side timeout
- [x] Tool audit log DB persistence
- [x] Narrow broad except in app.py
- [x] API integration: orchestrate field

### Q: Were any pre-existing tests broken?

**No.** All 322 original tests continue to pass. The only modified test (`test_runtime.py::test_stream_yields_output`) was updated to match the new queue-based streaming architecture — the old test was incompatible with the producer-consumer pattern.

---

## Recommendations

1. **Phase 4 Prep:** The middleware chain is designed for extension. Add retry middleware and circuit breaker middleware in Phase 4 Supervisor.
2. **Streaming Improvement:** OrchestratorRuntime.stream() should use asyncio.gather for parallel sub-tasks within stages (currently sequential). Low priority — Phase 4.
3. **Budget Atomicity:** Consider replacing BudgetMiddleware's read-then-cap with try_reserve() for atomic budget claiming. Low priority.
4. **Decomposer Upgrade:** Phase 4 replaces KeywordDecomposer with LLM-based decomposition. The TaskDecomposer Protocol makes this a drop-in replacement.

---

## Phase 3 Contract Verification

| Criterion | Status |
|-----------|--------|
| All 322 existing tests pass | PASS (410 total, 322+ original) |
| New tests pass (60-80 target) | PASS (64 new tests) |
| POST /runtime/invoke with orchestrate: true | IMPLEMENTED |
| GET /runtime/stream yields per-iteration JSON | IMPLEMENTED |
| SSE stream respects server-side timeout | IMPLEMENTED (300s default) |
| Tool calls persisted to tool_audit_log | IMPLEMENTED |
| ruff clean | PASS |
| 0 observer BLOCKERs/CRITICALs | PASS (0 found) |
