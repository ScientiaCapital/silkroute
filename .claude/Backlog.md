# SilkRoute Backlog

**Updated:** 2026-03-01 (Phase 6 complete)

## Priority: High (resolve in Phase 6b/7)

| # | Item | Source | Effort | Impact | Owner | ETA |
|---|------|--------|--------|--------|-------|-----|
| 1 | Wire ContextManager into SupervisorRuntime._run_session() (wrap plan.context) | Phase 5 plan gap | S | Medium | --- | Phase 6b |
| 3 | Add skill_executions DB repository (table exists, no write code) | Phase 5 plan gap | S | Medium | --- | Phase 6b |
| 5 | Broad `except Exception` in retry loops (orchestrator:270, supervisor:313) | Devil's Advocate (Phase 4) | S | Low | --- | Phase 7 |
| 7 | Budget snapshot daily rollups | Backlog carry-forward | M | Medium | --- | Phase 7 |

## Priority: Medium (resolve in Phase 7+)

| # | Item | Source | Effort | Impact | Owner | ETA |
|---|------|--------|--------|--------|-------|-----|
| 4 | Cache SkillRegistry as app.state in API (currently per-request creation) | Observer INFO (Phase 5) | XS | Low | --- | Phase 7 |
| 6 | Process rlimit enforcement (memory cap) | Observer WARNING (Phase 0) | M | Low | --- | Docker phase |
| 8 | Add test for lifespan Redis/DB connect+disconnect | Observer WARNING (Phase 2) | S | Low | --- | Phase 7 |
| 9 | Add test for SSE stream error path (`[ERROR]` event) | Observer WARNING (Phase 2) | XS | Low | --- | Phase 7 |
| 10 | CLI commands (skills list/info, context7 resolve/query, projects) not unit-tested | Observer INFO (Phase 5+6) | S | Low | --- | Phase 7 |
| 17 | Dashboard ESLint configuration (`next lint` requires setup) | Observer INFO (Phase 6) | XS | Low | --- | Phase 7 |

## Priority: Low (future phases)

| # | Item | Source | Effort | Impact | Owner | ETA |
|---|------|--------|--------|--------|-------|-----|
| 11 | Auto-sync TypeScript models from Python | Backlog carry-forward | L | Low | --- | Future |
| 12 | GitHub webhooks (HTTP listener) | Phase 7 Full | L | Medium | --- | Future |
| 13 | WebSocket for dashboard live updates | Phase 7 Full | L | Medium | --- | Future |
| 14 | Background daemonization (fork/detach) | Phase 7 Full | M | Medium | --- | Future |
| 15 | API rate limiting tiers | Plan scope exclusion (Phase 2) | M | Medium | --- | Future |
| 16 | Ralph autonomy boundary — no human approval gate | Observer R1 (Phase 4) | M | Low | --- | Future |
| 18 | Task history page in dashboard | Phase 6 plan deferral | M | Medium | --- | Phase 6b |

## Resolved (This Session — Phase 6)

| Item | Resolution |
|------|-----------|
| Consolidate SSRF protection into shared util (#2) | RESOLVED — unified in `network/ssrf.py`, both tools.py and http_skill.py import from it |
| SSRF dual implementation drift risk | RESOLVED — single source of truth eliminates drift |

## Resolved (Previous Sessions)

| Item | Resolution |
|------|-----------|
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
