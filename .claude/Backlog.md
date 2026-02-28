# SilkRoute Backlog

**Updated:** 2026-02-28 (Phase 3 complete)

## Priority: High (resolve in Phase 4)

| # | Item | Source | Effort | Impact | Owner | ETA |
|---|------|--------|--------|--------|-------|-----|
| 1 | OrchestratorRuntime.stream() broad `except Exception` — narrow to known exceptions | Observer W1 (Phase 3) | XS | Low | — | Phase 4 |
| 2 | BudgetMiddleware reads remaining_usd outside lock — use try_reserve() for atomic claim | Observer W2 (Phase 3) | S | Low | — | Phase 4 |
| 3 | OrchestratorRuntime.stream() processes sub-tasks sequentially within stages | Observer R2 (Phase 3) | M | Medium | — | Phase 4 |

## Priority: Medium (resolve in Phase 4-5)

| # | Item | Source | Effort | Impact | Owner | ETA |
|---|------|--------|--------|--------|-------|-----|
| 4 | `allocate_budget()` mutates sub-tasks in place — return copies | Observer W3 (Phase 3) | XS | Low | — | Phase 4 |
| 5 | `_split_compound()` naive " and " splitting in natural prose | Observer W4 (Phase 3) | N/A | Medium | — | Phase 4 (LLM decomposer replaces) |
| 6 | Process rlimit enforcement (memory cap) | Observer WARNING (Phase 0) | M | Low | — | Docker phase |
| 7 | Budget snapshot daily rollups | Backlog carry-forward | M | Medium | — | Phase 4 |
| 8 | Add test for lifespan Redis/DB connect+disconnect | Observer WARNING (Phase 2) | S | Low | — | Phase 4 |
| 9 | Add test for SSE stream error path (`[ERROR]` event) | Observer WARNING (Phase 2) | XS | Low | — | Phase 4 |

## Priority: Low (future phases)

| # | Item | Source | Effort | Impact | Owner | ETA |
|---|------|--------|--------|--------|-------|-----|
| 10 | Auto-sync TypeScript models from Python | Backlog carry-forward | L | Low | — | Phase 6 |
| 11 | GitHub webhooks (HTTP listener) | Phase 7 Full | L | Medium | — | Phase 4+ |
| 12 | WebSocket for dashboard live updates | Phase 7 Full | L | Medium | — | Phase 6 |
| 13 | Background daemonization (fork/detach) | Phase 7 Full | M | Medium | — | Phase 4 |
| 14 | API rate limiting tiers | Plan scope exclusion (Phase 2) | M | Medium | — | Phase 4+ |

## Resolved (This Session — Phase 3)

| Item | Resolution |
|------|-----------|
| Tool audit log persistence (#1 from Phase 2 backlog) | RESOLVED — `db/repositories/tool_audit.py` + wired into `_schedule_db_writes()` |
| LegacyRuntime.stream() batch-not-stream (#2) | RESOLVED — asyncio.Queue producer-consumer pattern |
| Narrow `app.py` broad `except Exception` (#3) | RESOLVED — narrowed to `(OSError, asyncpg.PostgresError, asyncpg.InterfaceError, ValueError)` |
| SSE stream endpoint no timeout (#4) | RESOLVED — `stream_timeout_seconds: 300` in ApiConfig + asyncio.timeout() |
| Document threading model for `_sandbox_config` (#6) | RESOLVED — docstring added to agent/tools.py |
| Extract duplicate `test_settings` fixture (#10) | RESOLVED — shared fixture in tests/conftest.py |
| Runtime invoke timeout configurable (#15) | RESOLVED — stream_timeout_seconds in ApiConfig |

---

_Effort: XS (<1hr), S (1-3hr), M (3-8hr), L (1-2d)_
