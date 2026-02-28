# SilkRoute Backlog

**Updated:** 2026-02-28 (Phase 2 complete)

## Priority: High (resolve in Phase 3)

| # | Item | Source | Effort | Impact | Owner | ETA |
|---|------|--------|--------|--------|-------|-----|
| 1 | Tool audit log persistence to `tool_audit_log` DB table | Observer WARNING (Phase 0) | S | Medium | — | Phase 3 |
| 2 | LegacyRuntime.stream() is batch-not-stream (SSE stream endpoint degrades) | Observer SMELL (Phase 0) | M | Medium | — | Phase 3 |
| 3 | Narrow `app.py:59` broad `except Exception` to `(OSError, asyncpg.PostgresError)` | Observer WARNING (Phase 2) | XS | Low | — | Phase 3 |
| 4 | SSE stream endpoint has no server-side timeout/max-duration | Observer WARNING (Phase 2 Arch) | S | Medium | — | Phase 3 |

## Priority: Medium (resolve in Phase 3-4)

| # | Item | Source | Effort | Impact | Owner | ETA |
|---|------|--------|--------|--------|-------|-----|
| 5 | Process rlimit enforcement (memory cap) | Observer WARNING (Phase 0) | M | Low | — | Phase 3 (Docker) |
| 6 | Document threading model assumption for `_sandbox_config` | Observer RISK (Phase 0) | XS | Low | — | Phase 3 |
| 7 | Budget snapshot daily rollups | Backlog carry-forward | M | Medium | — | Phase 3 |
| 8 | Add test for lifespan Redis/DB connect+disconnect | Observer WARNING (Phase 2) | S | Low | — | Phase 3 |
| 9 | Add test for SSE stream error path (`[ERROR]` event) | Observer WARNING (Phase 2) | XS | Low | — | Phase 3 |
| 10 | Extract duplicate `test_settings` fixture to shared API conftest | Observer INFO (Phase 2) | XS | Low | — | Phase 3 |

## Priority: Low (future phases)

| # | Item | Source | Effort | Impact | Owner | ETA |
|---|------|--------|--------|--------|-------|-----|
| 11 | Auto-sync TypeScript models from Python | Backlog carry-forward | L | Low | — | Phase 6 |
| 12 | GitHub webhooks (HTTP listener) | Phase 7 Full | L | Medium | — | Phase 4+ |
| 13 | WebSocket for dashboard live updates | Phase 7 Full | L | Medium | — | Phase 6 |
| 14 | Background daemonization (fork/detach) | Phase 7 Full | M | Medium | — | Phase 4 |
| 15 | Runtime invoke timeout configurable (currently hardcoded 300s) | Observer INFO (Phase 2 Arch) | XS | Low | — | Phase 3 |
| 16 | API rate limiting tiers | Plan scope exclusion (Phase 2) | M | Medium | — | Phase 4+ |

## Resolved (This Session — Phase 2)

| Item | Resolution |
|------|-----------|
| REST API / HTTP control plane (Backlog #8) | RESOLVED — 11 endpoints at `localhost:8787`, full test suite |
| `silkroute api` CLI command | RESOLVED — uvicorn launcher with --host/--port/--reload |
| Bearer token auth | RESOLVED — `secrets.compare_digest()`, dev mode when key empty |
| Queue backpressure HTTP surface | RESOLVED — 429 on full, 503 on Redis down |
| Budget governance via HTTP | RESOLVED — fail-open when Postgres unavailable |
| Model catalog endpoint | RESOLVED — filterable by tier/capability, URL-encoded IDs |

---

_Effort: XS (<1hr), S (1-3hr), M (3-8hr), L (1-2d)_
