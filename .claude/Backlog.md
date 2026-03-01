# SilkRoute Backlog

**Updated:** 2026-03-01 (Phase 5 complete)

## Priority: High (resolve in Phase 6)

| # | Item | Source | Effort | Impact | Owner | ETA |
|---|------|--------|--------|--------|-------|-----|
| 1 | Wire ContextManager into SupervisorRuntime._run_session() (wrap plan.context) | Phase 5 plan gap | S | Medium | --- | Phase 6 |
| 2 | Consolidate SSRF protection into shared util (agent/tools.py + builtin/http_skill.py drift risk) | Observer WARN (Phase 5) | S | Medium | --- | Phase 6 |
| 3 | Add skill_executions DB repository (table exists, no write code) | Phase 5 plan gap | S | Medium | --- | Phase 6 |
| 4 | Cache SkillRegistry as app.state in API (currently per-request creation) | Observer INFO (Phase 5) | XS | Low | --- | Phase 6 |

## Priority: Medium (resolve in Phase 6-7)

| # | Item | Source | Effort | Impact | Owner | ETA |
|---|------|--------|--------|--------|-------|-----|
| 5 | Broad `except Exception` in retry loops (orchestrator:270, supervisor:313) | Devil's Advocate (Phase 4) | S | Low | --- | Phase 6 |
| 6 | Process rlimit enforcement (memory cap) | Observer WARNING (Phase 0) | M | Low | --- | Docker phase |
| 7 | Budget snapshot daily rollups | Backlog carry-forward | M | Medium | --- | Phase 6 |
| 8 | Add test for lifespan Redis/DB connect+disconnect | Observer WARNING (Phase 2) | S | Low | --- | Phase 6 |
| 9 | Add test for SSE stream error path (`[ERROR]` event) | Observer WARNING (Phase 2) | XS | Low | --- | Phase 6 |
| 10 | CLI commands (skills list/info, context7 resolve/query) not unit-tested | Observer INFO (Phase 5) | S | Low | --- | Phase 6 |

## Priority: Low (future phases)

| # | Item | Source | Effort | Impact | Owner | ETA |
|---|------|--------|--------|--------|-------|-----|
| 11 | Auto-sync TypeScript models from Python | Backlog carry-forward | L | Low | --- | Phase 6 |
| 12 | GitHub webhooks (HTTP listener) | Phase 7 Full | L | Medium | --- | Phase 6+ |
| 13 | WebSocket for dashboard live updates | Phase 7 Full | L | Medium | --- | Phase 6 |
| 14 | Background daemonization (fork/detach) | Phase 7 Full | M | Medium | --- | Phase 6+ |
| 15 | API rate limiting tiers | Plan scope exclusion (Phase 2) | M | Medium | --- | Phase 6+ |
| 16 | Ralph autonomy boundary — no human approval gate | Observer R1 (Phase 4) | M | Low | --- | Phase 6 (dashboard) |

## Resolved (This Session --- Phase 5)

| Item | Resolution |
|------|-----------|
| Broad `except Exception` in RalphController.run_cycle() (W1) | RESOLVED --- narrowed to (RuntimeError, OSError, ValueError, TimeoutError) |
| Silent checkpoint failure logging (W2) | RESOLVED --- log.warning with error string in supervisor/runtime.py |
| Naive keyword decomposer (W4) | RESOLVED --- LLMDecomposer with LRU cache and KeywordDecomposer fallback |

## Resolved (Previous Sessions)

| Item | Resolution |
|------|-----------|
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
