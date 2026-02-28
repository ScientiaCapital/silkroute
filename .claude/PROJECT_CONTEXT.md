# silkroute

**Branch**: main | **Updated**: 2026-02-28

## Status
Phase 3 (Multi-Agent Orchestration) complete on `main`. OrchestratorRuntime with DAG-based stage execution, middleware chain, keyword decomposer, true per-iteration streaming, SSE timeout, tool audit persistence, and backlog cleanup. 410/410 tests passing. Lint clean. 0 observer BLOCKERs/CRITICALs.

## Done (This Session — Phase 3)
- [x] Created `mantis/orchestrator/` package: models, decomposer, budget, middleware, aggregator, runtime (7 modules)
- [x] OrchestratorRuntime implementing AgentRuntime Protocol with DAG stage execution
- [x] KeywordDecomposer + SingleTaskDecomposer (no LLM, keyword-based splitting)
- [x] Middleware chain: ValidationMiddleware → BudgetMiddleware → LoggingMiddleware
- [x] BudgetTracker with asyncio.Lock for concurrent sub-agent spend tracking
- [x] True per-iteration streaming via asyncio.Queue in run_agent() + LegacyRuntime.stream()
- [x] SSE server-side timeout (stream_timeout_seconds: 300 in ApiConfig)
- [x] Tool audit log persistence (db/repositories/tool_audit.py wired into _schedule_db_writes)
- [x] Narrowed broad except in app.py to (OSError, asyncpg.PostgresError, asyncpg.InterfaceError, ValueError)
- [x] Shared test_settings fixture, removed duplicates from 3 test files
- [x] API: `orchestrate: bool` field on RuntimeInvokeRequest, routes to OrchestratorRuntime
- [x] 64 new tests (410 total), ruff clean, gitleaks clean

## Blockers
None

## Tomorrow
Tomorrow: Phase 4 (Supervisor + Ralph Mode) via planning-prompts | Sonnet builder + Haiku observer | Est: 1-2 sessions, ~$5 | Observer notes: W1 broad except in orchestrator stream, W2 non-atomic budget read, R2 sequential streaming in orchestrator

## Tech Stack
Python 3.12 (Click + Pydantic + FastAPI + uvicorn + litellm + asyncpg + structlog + Rich + redis + apscheduler + deepagents + langchain-openai) | Next.js 15 (React 19, Tailwind v4) | PostgreSQL 16 | Redis 7 | LiteLLM | Docker Compose

## Session Stats
- New files: 13 (8 source + 5 test)
- Modified files: 22 (9 source + 13 test)
- Tests: 346 existing + 64 new = 410 total, all passing
- Lint: clean (ruff check)
- Security: gitleaks clean, 0 secrets
- Lines: +1,576 / -107 (915 backend new, 139 backend modified, 1,097 test new)
- Observer: 0 BLOCKER, 0 CRITICAL, 4 WARNING, 2 RISK (all logged to Backlog)

## Links
- GitHub: https://github.com/ScientiaCapital/silkroute
- Vercel: https://silkroute-sepia.vercel.app
- Dashboard (local): http://localhost:3000
- API docs (local): http://localhost:8787/docs

---

_Updated by Phase 3 completion. 2026-02-28._
