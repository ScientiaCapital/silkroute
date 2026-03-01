# Feature Contract: Phase 7 — Daemon Hardening + Budget Rollups

**Date:** 2026-03-01
**Scope:** STANDARD (10-15 files, no new dependencies)

## Build Targets

### Task A: Exception Hardening (#5)

**Goal:** Replace broad `except Exception` with specific exception types in retry loops, DB operations, and tool handlers.

**Priority tiers:**
- CRITICAL (3 instances): Retry loops in `runtime.py:278`, `worker.py:90`, `loop.py:108`
- HIGH (6 instances): DB init/close in `loop.py:159,238,359`, `lifecycle.py:111,156,166`
- MEDIUM (10 instances): Skill/tool execution in `registry.py`, `tools.py`, builtin skills
- LOW (32 instances): API routes, CLI handlers, graceful fallbacks

**Rules:**
- `asyncio.CancelledError` MUST always propagate (never swallow)
- Retry loops MUST distinguish transient (retryable) from permanent (not retryable) failures
- Graceful degradation catches (DB optional) keep broad catch but use specific types first
- All catches MUST log at appropriate level (debug/warning/error)
- Silent `except Exception: pass` patterns MUST add at minimum debug logging

**Files modified:**
- `src/silkroute/mantis/orchestrator/runtime.py`
- `src/silkroute/daemon/worker.py`
- `src/silkroute/agent/loop.py`
- `src/silkroute/daemon/lifecycle.py`
- `src/silkroute/mantis/skills/registry.py`
- `src/silkroute/agent/tools.py`
- `src/silkroute/mantis/skills/builtin/*.py`
- `src/silkroute/api/routes/health.py`
- `src/silkroute/api/routes/budget.py`

**Verification:**
- [ ] All 785+ tests still pass
- [ ] No bare `except Exception: pass` remains (all have logging)
- [ ] `asyncio.CancelledError` is never caught (always propagated)
- [ ] Retry loops catch transient exceptions separately from permanent ones
- [ ] `ruff check src/` clean

---

### Task B: Budget Snapshot Daily Rollups (#7)

**Goal:** Populate the existing `budget_snapshots` table with daily aggregations from `cost_logs`.

**New files:**
- `src/silkroute/db/repositories/budget_snapshots.py` — rollup + query functions
- `tests/test_budget_snapshots.py` — unit tests for rollup logic

**Modified files:**
- `src/silkroute/daemon/scheduler.py` — add daily rollup cron job
- `src/silkroute/api/routes/budget.py` — add `GET /budget/snapshots` endpoint (optional)

**Design:**
- Rollup function: `INSERT INTO budget_snapshots ... SELECT ... FROM cost_logs WHERE date = $1 GROUP BY project_id ON CONFLICT (project_id, snapshot_date) DO UPDATE`
- Idempotent: re-running for the same date overwrites safely (UPSERT)
- Scheduled: APScheduler cron job at 00:05 UTC daily
- Backfill: CLI command or function to roll up historical dates
- Query: `get_snapshots(project_id, start_date, end_date)` for dashboard consumption

**Verification:**
- [ ] Rollup function is idempotent (re-run produces same result)
- [ ] Cron job registered in scheduler
- [ ] Tests cover: normal rollup, empty day, multiple projects, re-run idempotency
- [ ] All existing budget tests still pass

---

### Task C: SkillRegistry Caching (#4)

**Goal:** Convert SkillRegistry from per-request instantiation to app.state singleton.

**Modified files:**
- `src/silkroute/api/app.py` — create registry in lifespan, store on `app.state.skill_registry`
- `src/silkroute/api/deps.py` — add `get_skill_registry()` dependency function
- `src/silkroute/api/routes/skills.py` — replace `_get_registry()` with `Depends(get_skill_registry)`
- `tests/test_api_skills.py` — update fixtures to set `app.state.skill_registry`

**Pattern:** Follows exact same pattern as `app.state.redis`, `app.state.queue`, `app.state.db_pool`.

**Verification:**
- [ ] `GET /skills` returns same results as before
- [ ] `GET /skills/{skill_id}` returns same results as before
- [ ] Registry created once at startup, not per-request
- [ ] Tests pass with mock/fixture registry
- [ ] `_get_registry()` helper removed from skills route

---

## OUT OF SCOPE

- New pip dependencies
- Dashboard changes (no frontend work this phase)
- SupervisorSessionResponse helper extraction (#19) — deferred
- Supervisor route ordering documentation (#20) — deferred
- Process rlimit enforcement — deferred to containerization
- Any changes to the LLM provider layer

## Observer Checkpoints

- [ ] Observer spawned before code changes
- [ ] Architecture Observer approves contract
- [ ] Code Quality Observer runs after builder commits
- [ ] Final Observer report before merge
- [ ] Devil's Advocate sign-off at each gate
