# SilkRoute Backlog

**Updated:** 2026-03-01 (Phase 7 complete)

## Priority: High (resolve in Phase 8)

| # | Item | Source | Effort | Impact | Owner | ETA |
|---|------|--------|--------|--------|-------|-----|
| 8 | Add test for lifespan Redis/DB connect+disconnect | Observer WARNING (Phase 2) | S | Medium | --- | Phase 8 |
| 10 | CLI commands (skills list/info, context7 resolve/query, projects) not unit-tested | Observer INFO (Phase 5+6) | S | Medium | --- | Phase 8 |

## Priority: Medium

| # | Item | Source | Effort | Impact | Owner | ETA |
|---|------|--------|--------|--------|-------|-----|
| 6 | Process rlimit enforcement (memory cap) | Observer WARNING (Phase 0) | M | Low | --- | Docker phase |
| 9 | Add test for SSE stream error path (`[ERROR]` event) | Observer WARNING (Phase 2) | XS | Low | --- | Phase 8 |
| 17 | Dashboard ESLint configuration (`next lint` requires setup) | Observer INFO (Phase 6) | XS | Low | --- | Phase 8 |
| 19 | SupervisorSessionResponse construction repeated in 3 routes — extract helper | Observer INFO (Phase 6b) | XS | Low | --- | Phase 8 |
| 20 | Supervisor route ordering risk: future routes must maintain GET /sessions before GET /sessions/{id} | Observer INFO (Phase 6b) | XS | Low | --- | Phase 8 |
| 21 | `_extract_cost()` still has silent `except Exception: pass` (canonical pattern) | Observer INFO (Phase 7) | XS | Low | --- | Future |
| 22 | Pre-existing test failures: 6 deepagents + 1 langchain_openai collection error | Observer INFO (Phase 7) | S | Low | --- | Future |

## Priority: Low (future phases)

| # | Item | Source | Effort | Impact | Owner | ETA |
|---|------|--------|--------|--------|-------|-----|
| 11 | Auto-sync TypeScript models from Python | Backlog carry-forward | L | Low | --- | Future |
| 12 | GitHub webhooks (HTTP listener) | Phase 7 Full | L | Medium | --- | Future |
| 13 | WebSocket for dashboard live updates | Phase 7 Full | L | Medium | --- | Future |
| 14 | Background daemonization (fork/detach) | Phase 7 Full | M | Medium | --- | Future |
| 15 | API rate limiting tiers | Plan scope exclusion (Phase 2) | M | Medium | --- | Future |
| 16 | Ralph autonomy boundary — no human approval gate | Observer R1 (Phase 4) | M | Low | --- | Future |

## Resolved (This Session — Phase 7)

| Item | Resolution |
|------|-----------|
| Broad `except Exception` in retry loops (#5) | RESOLVED — four-clause pattern (CancelledError/transient/permanent/fallback) across 9 files |
| Budget snapshot daily rollups (#7) | RESOLVED — budget_snapshots.py repo + scheduler cron + GET /budget/snapshots endpoint |
| Cache SkillRegistry as app.state (#4) | RESOLVED — app.state.skill_registry singleton via Depends(get_skill_registry) |

## Resolved (Phase 6b)

| Item | Resolution |
|------|-----------|
| Wire ContextManager into SupervisorRuntime (#1) | RESOLVED — dual-write pattern in _run_session() + stream() + _execute_step() |
| Add skill_executions DB repository (#3) | RESOLVED — skill_executions.py with INSERT, LIST, STATS + fire-and-forget in SkillRegistry |
| Task history page in dashboard (#18) | RESOLVED — tasks/page.tsx with session cards, step progress bars, status badges |

## Resolved (Previous Sessions)

| Item | Resolution |
|------|-----------|
| Consolidate SSRF protection into shared util (#2) | RESOLVED — unified in `network/ssrf.py` (Phase 6) |
| SSRF dual implementation drift risk | RESOLVED — single source of truth (Phase 6) |
| Broad `except Exception` in RalphController.run_cycle() (W1) | Narrowed to specific types (Phase 5) |
| Silent checkpoint failure logging (W2) | log.warning with error string (Phase 5) |
| Naive keyword decomposer (W4) | LLMDecomposer with cache + fallback (Phase 5) |
| OrchestratorRuntime.stream() broad except | Narrowed to specific exceptions (Phase 4) |
| BudgetMiddleware non-atomic budget | try_reserve()/settle() with asyncio.Lock (Phase 4) |
| OrchestratorRuntime.stream() sequential stages | asyncio.gather for parallel (Phase 4) |
| allocate_budget() mutates in place | copy.deepcopy (Phase 4) |
| Tool audit log persistence | db/repositories/tool_audit.py (Phase 3) |
| LegacyRuntime.stream() batch-not-stream | asyncio.Queue producer-consumer (Phase 3) |
| app.py broad except Exception | Narrowed to specific types (Phase 3) |
| SSE stream no timeout | stream_timeout_seconds: 300 (Phase 3) |
| Document _sandbox_config threading model | Docstring in tools.py (Phase 3) |
| Duplicate test_settings fixture | Shared in conftest.py (Phase 3) |

---

_Effort: XS (<1hr), S (1-3hr), M (3-8hr), L (1-2d)_
