# Phase 8 Feature Contract: Test Coverage Gaps + CLI Testing

**Created:** 2026-03-01
**Scope:** STANDARD (4 files changed/created, no new deps)
**Type:** Test-only — no new features, no architectural changes

## Acceptance Criteria

1. **Lifespan tests** (`tests/test_lifespan.py` — NEW):
   - Redis connect success: mock `aioredis.from_url()` + `ping()`, verify `app.state.redis` set, `app.state.queue` is TaskQueue
   - Redis connect failure: mock raising `ConnectionError`, verify `app.state.redis = None`
   - Postgres connect success: mock `asyncpg.create_pool()`, verify `app.state.db_pool` set
   - Postgres connect failure: mock raising `OSError`, verify `app.state.db_pool = None`
   - SkillRegistry initialization: verify `app.state.skill_registry` exists with builtin skills
   - Cleanup: Redis `aclose()` called on shutdown
   - Cleanup: DB pool `close()` called on shutdown
   - Cleanup when None: no error when redis/pool are None at shutdown

2. **SSE error path tests** (`tests/test_api_runtime.py` — EXTEND):
   - Timeout error: verify `[ERROR] Stream timed out` in response
   - Generic exception: verify `[ERROR] boom` in response
   - No `[DONE]` on error paths

3. **CLI unit tests** (`tests/test_cli.py` — NEW):
   - Simple commands: `--version`, `status`, `models`, `models --tier free`, `budget`, `init`
   - Skills: `skills list`, `skills list --category invalid`, `skills info <name>`, `skills info nonexistent`
   - Context7: `context7 resolve` (success/not-found/error), `context7 query` (success/error)
   - Projects: `projects list` (populated/empty), `projects create`, `projects show` (found/missing), `projects delete --yes`

4. **Zero regressions**: All existing ~800 tests still pass
5. **Lint clean**: `ruff check src/ tests/` passes
6. **Observer**: 0 CRITICALs, 0 BLOCKERs

## Non-Goals

- No new production code
- No new dependencies
- No architectural changes
