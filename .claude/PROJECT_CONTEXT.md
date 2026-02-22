# silkroute

**Branch**: feature/phase7a-core-daemon | **Updated**: 2026-02-22

## Status
Phase 7b (Redis Queue + APScheduler Cron) complete on `feature/phase7a-core-daemon` branch. Daemon now persists tasks in Redis (LIST/HASH/STRING), survives restarts without data loss, and has APScheduler cron jobs for nightly scans + weekly dependency audits. 176/176 tests passing. Lint clean.

## Done (This Session — Phase 7b)
- [x] Created daemon/redis_pool.py — async Redis singleton with retry decorator (mirrors db/pool.py)
- [x] Created daemon/serialization.py — JSON round-trip for TaskRequest/TaskResult via dataclasses.asdict
- [x] Created daemon/scheduler.py — DaemonScheduler with APScheduler + RedisJobStore, 2 built-in cron jobs
- [x] Rewrote daemon/queue.py — asyncio.Queue replaced with Redis LIST/HASH/STRING
- [x] Updated daemon/worker.py — `await queue.record_result(result)` (now async)
- [x] Updated daemon/server.py — Redis pool wiring, scheduler lifecycle, async status with scheduler_jobs
- [x] Updated daemon/lifecycle.py — Redis init (required) and shutdown in DaemonContext
- [x] Updated daemon/heartbeat.py — async `_emit_heartbeat()` for Redis `pending_count()`
- [x] Updated daemon/__init__.py — added DaemonScheduler, get_redis, close_redis exports
- [x] Removed unused deps: supabase, prometheus-client from pyproject.toml
- [x] Added fakeredis>=2.21.0 to dev deps
- [x] Created tests/conftest.py with fakeredis fixture
- [x] Created tests/test_redis_pool.py (11 tests), test_serialization.py (9 tests), test_daemon_scheduler.py (10 tests)
- [x] Refactored tests/test_daemon_queue.py, test_daemon_worker.py, test_daemon_server.py, test_daemon_heartbeat.py for fakeredis
- [x] Feature contract: .claude/contracts/phase7b-redis-scheduler.md
- [x] Observer-full ran — PASS, no BLOCKERs
- [x] Security gate: 176/176 tests, lint clean, gitleaks clean

## Blockers
None

## Backlog (carried + new)

### Phase 7 Full (next sprint)
- [ ] GitHub webhooks (HTTP listener)
- [ ] REST API / HTTP control plane
- [ ] WebSocket for dashboard live updates
- [ ] Background daemonization (fork/detach)
- [ ] Custom scheduled tasks from DB (`load_custom_jobs` stub)
- [ ] In-flight task crash recovery (Redis SET for in-progress tasks)
- [ ] Integration smoke test: start daemon, submit task, verify end-to-end

### Carried from Phase 3+
- [ ] Tool audit log persistence
- [ ] Budget snapshot daily rollups
- [ ] Dashboard API integration with Postgres
- [ ] Add `terminal_reason` column to `agent_sessions`
- [ ] Budget alert webhooks — Slack/Telegram
- [ ] MCP tool servers — GitHub, Supabase, Brave (Phase 5)
- [ ] Ollama local model routing (Phase 6)

### Housekeeping (carried)
- [ ] `_active_worker_count` never incremented in server.py (heartbeat reports 0)
- [ ] Auto-sync TypeScript models from Python
- [ ] Add daemon_mode=True tests to test_loop.py (observer flag)
- [ ] Lifecycle test file for PID file + stale PID scenarios
- [ ] Test for lifecycle.py Redis startup failure path (RuntimeError)

## Next Handoff
Tomorrow: Phase 7 Full (webhooks + REST API) via planning-prompts-skill | 2 builders (Sonnet) | Est: 3h, $8-12 | Observer notes: `_active_worker_count` never incremented (cosmetic)

## Tech Stack
Python 3.12 (Click + Pydantic + litellm + asyncpg + structlog + Rich + redis + apscheduler) | Next.js 15 (React 19, Tailwind v4) | PostgreSQL 16 | Redis 7 | LiteLLM | Docker Compose

## Session Stats
- New files: 8 (3 source + 3 test + 1 conftest + 1 contract)
- Modified files: 11 (7 source/config + 4 test)
- Lines shipped: ~577 new + ~399 modified = ~976 total
- Tests: 140 existing + 36 new = 176 total, all passing
- Observer findings: 0 BLOCKERs, 2 WARNINGs (carried, not new)
- Deps cleaned: -2 unused runtime (supabase, prometheus-client), +1 dev (fakeredis)

## Links
- GitHub: https://github.com/ScientiaCapital/silkroute
- Vercel: https://silkroute-sepia.vercel.app
- Dashboard (local): http://localhost:3000

---

_Updated by Phase 7b completion. 2026-02-22._
