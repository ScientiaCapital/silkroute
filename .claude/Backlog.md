# SilkRoute Backlog

**Updated:** 2026-02-28 (Phase 4 complete)

## Priority: High (resolve in Phase 5)

| # | Item | Source | Effort | Impact | Owner | ETA |
|---|------|--------|--------|--------|-------|-----|
| 1 | Narrow broad `except Exception` in RalphController.run_cycle() (ralph.py:82) | Observer W1 (Phase 4) | S | Low | --- | Phase 5 |
| 2 | Add checkpoint verification in Ralph Mode cycles (detect silently lost checkpoints) | Observer W2 (Phase 4) | S | Medium | --- | Phase 5 |
| 3 | `_split_compound()` naive " and " splitting in natural prose — replace with LLM decomposer | Observer W4 (Phase 3) | M | Medium | --- | Phase 5 (LLM decomposer) |

## Priority: Medium (resolve in Phase 5-6)

| # | Item | Source | Effort | Impact | Owner | ETA |
|---|------|--------|--------|--------|-------|-----|
| 4 | Broad `except Exception` in retry loops (orchestrator:270, supervisor:313) | Devil's Advocate (Phase 4) | S | Low | --- | Phase 5 |
| 5 | Process rlimit enforcement (memory cap) | Observer WARNING (Phase 0) | M | Low | --- | Docker phase |
| 6 | Budget snapshot daily rollups | Backlog carry-forward | M | Medium | --- | Phase 5 |
| 7 | Add test for lifespan Redis/DB connect+disconnect | Observer WARNING (Phase 2) | S | Low | --- | Phase 5 |
| 8 | Add test for SSE stream error path (`[ERROR]` event) | Observer WARNING (Phase 2) | XS | Low | --- | Phase 5 |

## Priority: Low (future phases)

| # | Item | Source | Effort | Impact | Owner | ETA |
|---|------|--------|--------|--------|-------|-----|
| 9 | Auto-sync TypeScript models from Python | Backlog carry-forward | L | Low | --- | Phase 6 |
| 10 | GitHub webhooks (HTTP listener) | Phase 7 Full | L | Medium | --- | Phase 5+ |
| 11 | WebSocket for dashboard live updates | Phase 7 Full | L | Medium | --- | Phase 6 |
| 12 | Background daemonization (fork/detach) | Phase 7 Full | M | Medium | --- | Phase 5 |
| 13 | API rate limiting tiers | Plan scope exclusion (Phase 2) | M | Medium | --- | Phase 5+ |
| 14 | Ralph autonomy boundary — no human approval gate (mitigated by budget+cron) | Observer R1 (Phase 4) | M | Low | --- | Phase 6 (dashboard) |

## Resolved (This Session --- Phase 4)

| Item | Resolution |
|------|-----------|
| OrchestratorRuntime.stream() broad `except Exception` (#1 Phase 3) | RESOLVED --- narrowed to (TimeoutError, BudgetExhaustedError, RuntimeError, OSError, ValueError) |
| BudgetMiddleware non-atomic budget read (#2 Phase 3) | RESOLVED --- try_reserve()/settle() pattern with asyncio.Lock |
| OrchestratorRuntime.stream() sequential within stages (#3 Phase 3) | RESOLVED --- asyncio.gather for parallel sub-task execution |
| `allocate_budget()` mutates in place (#4 Phase 3) | RESOLVED --- copy.deepcopy returns new plan |

## Resolved (Previous Sessions)

| Item | Resolution |
|------|-----------|
| Tool audit log persistence | db/repositories/tool_audit.py |
| LegacyRuntime.stream() batch-not-stream | asyncio.Queue producer-consumer |
| app.py broad `except Exception` | Narrowed to specific types |
| SSE stream endpoint no timeout | stream_timeout_seconds: 300 |
| Document _sandbox_config threading model | Docstring in tools.py |
| Duplicate test_settings fixture | Shared in conftest.py |

---

_Effort: XS (<1hr), S (1-3hr), M (3-8hr), L (1-2d)_
