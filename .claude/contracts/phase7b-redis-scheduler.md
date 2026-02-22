# Feature Contract: Phase 7b — Redis Queue + APScheduler Cron

**Date:** 2026-02-22
**Scope:** STANDARD (5 new files, 8 modified files, 2 existing deps activated, 1 new dev dep)

## IN SCOPE

- `daemon/redis_pool.py` — async Redis client singleton (mirrors db/pool.py)
- `daemon/serialization.py` — JSON round-trip for TaskRequest/TaskResult dataclasses
- `daemon/scheduler.py` — APScheduler with Redis job store, 2 built-in cron jobs
- Rewrite `daemon/queue.py` internals from asyncio.Queue to Redis LIST/HASH/STRING
- 3 new test files + 1 conftest fixture (`fakeredis`)
- Update `worker.py` — `await queue.record_result(result)`
- Update `server.py` — wire Redis pool, scheduler lifecycle, async status
- Update `lifecycle.py` — Redis init/shutdown in DaemonContext
- Update `heartbeat.py` — async `_emit_heartbeat()` for Redis `pending_count()`
- Update `__init__.py` — new exports
- Remove unused deps: `supabase`, `prometheus-client`
- Add dev dep: `fakeredis[aioredis]>=2.21.0`

## OUT OF SCOPE

- Custom scheduled tasks from DB (stubbed only)
- GitHub webhooks (Phase 7 Full)
- REST API / HTTP control plane (Phase 7 Full)
- In-flight task crash recovery (future enhancement)
- Background daemonization (fork/detach)
- Dashboard integration with scheduler status

## Redis Key Schema

| Key | Type | Purpose |
|-----|------|---------|
| `silkroute:queue:pending` | LIST | RPUSH to enqueue, BLPOP to dequeue (FIFO) |
| `silkroute:results` | HASH | field=request_id, value=JSON(TaskResult) |
| `silkroute:counter:submitted` | STRING | INCR on each submit() |
| `silkroute:counter:completed` | STRING | INCR on each record_result() |

## Key Design Decisions

1. JSON serialization via `dataclasses.asdict()` + custom `TaskEncoder`
2. `record_result()` and `get_result()` become async (Redis HSET/HGET)
3. `pending_count()` becomes async (Redis LLEN)
4. `total_submitted`/`total_completed` stay as properties (local shadow counters)
5. APScheduler 3.x with `AsyncIOScheduler` + `RedisJobStore`
6. Redis is required — daemon exits if unreachable at startup
7. Cron jobs submit directly to queue (no socket round-trip)
