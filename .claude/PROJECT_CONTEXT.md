# silkroute

**Branch**: main | **Updated**: 2026-02-28

## Status
Phase 0 (Security Hardening + Bug Fixes) complete on `main`. Shell sandbox with 25+ blocklist patterns and workspace confinement. Budget enforcement wired (daily/monthly caps + circuit breaker). All 3 carried WARNINGs fixed. Mantis runtime abstraction layer created (AgentRuntime Protocol + LegacyRuntime + DeepAgentsRuntime stub). 262/262 tests passing. Lint clean.

## Done (This Session — Phase 0)
- [x] Phase 0a: Shell sandbox (`agent/sandbox.py`) — blocklist, workspace enforcement, path traversal detection
- [x] Phase 0a: Integrated sandbox into `agent/tools.py` and `agent/loop.py`
- [x] Phase 0b: `check_global_budget()` with daily cap, monthly cap, circuit breaker ($2/hr)
- [x] Phase 0b: Added `get_daily_spend()` and `get_hourly_spend_rate()` to `db/repositories/projects.py`
- [x] Phase 0b: Wired global budget into `agent/loop.py`
- [x] Phase 0c: Fixed `_active_worker_count` in `daemon/server.py` (try/finally in `_worker_wrapper`)
- [x] Phase 0c: Added 2 daemon_mode tests to `test_loop.py`
- [x] Phase 0c: Created `test_lifecycle.py` with 13 tests (PID file scenarios, startup/shutdown)
- [x] Phase 0d: Created `mantis/runtime/` package (interface, legacy, deepagents stub, registry)
- [x] Phase 0d: Created `test_runtime.py` with 22 tests
- [x] Created `tests/test_sandbox.py` with 31 tests
- [x] Created `tests/test_budget_global.py` with 12 tests
- [x] Fixed F821 bug: `budget_config` referenced before definition in `loop.py`
- [x] Devil's Advocate review: 2 minor gaps documented (audit log DB persistence, rlimit enforcement)

## Blockers
None

## Backlog (carried + new)

### Phase 1: OpenRouter + Deep Agents Foundation (next)
- [ ] OpenRouter adapter via `langchain-openai` (NOT langchain-openrouter)
- [ ] First Deep Agent (Code Writer) with `create_deep_agent()`
- [ ] MantisConfig settings extension
- [ ] Dependencies: deepagents==0.4.1, langchain-openai>=0.3.0, langgraph>=0.2.0

### Phase 2: FastAPI REST Layer
- [ ] POST/GET /tasks, GET /daemon/status, POST /daemon/stop, GET /health
- [ ] FastAPI alongside Unix socket (no breaking change)

### Carried from Phase 0 (minor gaps)
- [ ] Tool audit log persistence to `tool_audit_log` table (structlog covers for now)
- [ ] Process resource limits (rlimit) — deferred to Docker containerization
- [ ] Budget snapshot daily rollups
- [ ] Auto-sync TypeScript models from Python
- [ ] Test for lifecycle.py Redis startup failure path (RuntimeError) — already tested

### Phase 7 Full (deferred)
- [ ] GitHub webhooks (HTTP listener)
- [ ] REST API / HTTP control plane
- [ ] WebSocket for dashboard live updates
- [ ] Background daemonization (fork/detach)

## Next Handoff
Tomorrow: Phase 1 (OpenRouter + Deep Agents Foundation) — OpenRouter adapter, first Deep Agent, settings extension. Est: 3 days. Requires: deepagents==0.4.1 pin investigation for API stability.

## Tech Stack
Python 3.12 (Click + Pydantic + litellm + asyncpg + structlog + Rich + redis + apscheduler) | Next.js 15 (React 19, Tailwind v4) | PostgreSQL 16 | Redis 7 | LiteLLM | Docker Compose

## Session Stats
- New files: 8 (4 source in mantis/ + sandbox.py + 4 test files)
- Modified files: 7 (tools.py, loop.py, cost_guard.py, server.py, projects.py, test_loop.py, test_tools.py)
- Tests: 176 existing + 86 new = 262 total, all passing
- Lint: clean (ruff check)
- Security: gitleaks clean, 0 secrets in src/

## Links
- GitHub: https://github.com/ScientiaCapital/silkroute
- Vercel: https://silkroute-sepia.vercel.app
- Dashboard (local): http://localhost:3000

---

_Updated by Phase 0 completion. 2026-02-28._
