# Phase 3: Multi-Agent Orchestration — Feature Contract

**Date**: 2026-02-28 | **Scope**: FULL

## IN SCOPE
- `mantis/orchestrator/` package (7 new modules)
- OrchestratorRuntime implementing AgentRuntime Protocol
- Task decomposition (keyword-based, no LLM calls)
- Sub-agent middleware chain (budget, logging, validation)
- DAG-based stage execution (parallel within stages, sequential between)
- Budget allocation across sub-agents with shared tracker
- Result aggregation into single AgentResult
- True per-iteration streaming for LegacyRuntime via asyncio.Queue
- SSE server-side timeout
- Tool audit log DB persistence
- Narrow broad except in app.py
- API integration: `orchestrate: bool` field on RuntimeInvokeRequest

## OUT OF SCOPE
- LLM-based task decomposition (Phase 4)
- Inter-sub-task communication / piped results (Phase 4 Supervisor)
- Retry logic for failed sub-tasks (Phase 4)
- New pip dependencies
- New DB tables (existing `tool_audit_log` table is used)
- New CLI commands
- Dashboard integration

## SUCCESS CRITERIA
- [ ] All 322 existing tests still pass
- [ ] New tests pass (est. 60-80 new tests)
- [ ] `POST /runtime/invoke` with `orchestrate: true` decomposes and delegates
- [ ] `GET /runtime/stream` yields per-iteration JSON chunks
- [ ] SSE stream respects server-side timeout
- [ ] Tool calls persisted to `tool_audit_log` table
- [ ] ruff clean, gitleaks clean
- [ ] 0 observer BLOCKERs / CRITICALs
