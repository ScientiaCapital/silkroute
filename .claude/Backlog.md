# SilkRoute Backlog

**Updated:** 2026-02-28

## Priority: High (resolve in Phase 2-3)

| # | Item | Source | Effort | Impact | Owner | ETA |
|---|------|--------|--------|--------|-------|-----|
| 1 | Tool audit log persistence to `tool_audit_log` DB table | Observer WARNING (Phase 0) | S | Medium | — | Phase 3 |
| 2 | LegacyRuntime.stream() is batch-not-stream | Observer SMELL (Phase 0) | M | Medium | — | Phase 2+ |

## Priority: Medium (resolve in Phase 3-4)

| # | Item | Source | Effort | Impact | Owner | ETA |
|---|------|--------|--------|--------|-------|-----|
| 3 | Process rlimit enforcement (memory cap) | Observer WARNING (Phase 0) | M | Low | — | Phase 3 (Docker) |
| 4 | Document threading model assumption for `_sandbox_config` | Observer RISK (Phase 0) | XS | Low | — | Phase 3 |
| 5 | Budget snapshot daily rollups | Backlog carry-forward | M | Medium | — | Phase 3 |

## Priority: Low (future phases)

| # | Item | Source | Effort | Impact | Owner | ETA |
|---|------|--------|--------|--------|-------|-----|
| 6 | Auto-sync TypeScript models from Python | Backlog carry-forward | L | Low | — | Phase 6 |
| 7 | GitHub webhooks (HTTP listener) | Phase 7 Full | L | Medium | — | Phase 4+ |
| 8 | REST API / HTTP control plane | Phase 7 Full | L | High | — | Phase 2 |
| 9 | WebSocket for dashboard live updates | Phase 7 Full | L | Medium | — | Phase 6 |
| 10 | Background daemonization (fork/detach) | Phase 7 Full | M | Medium | — | Phase 4 |

## Resolved (This Session)

| Item | Resolution |
|------|-----------|
| DeepAgentsRuntime stub raises NotImplementedError | RESOLVED — Phase 1 replaced stub with working implementation |
| OpenRouter adapter needed | RESOLVED — providers/openrouter.py created |
| MantisConfig settings extension | RESOLVED — added to config/settings.py |
| First Deep Agent (Code Writer) | RESOLVED — mantis/agents/code_writer.py |

---

_Effort: XS (<1hr), S (1-3hr), M (3-8hr), L (1-2d)_
