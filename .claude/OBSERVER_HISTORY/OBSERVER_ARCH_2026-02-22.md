# SilkRoute: Architecture Observer Report — Phase 3
**Date:** 2026-02-22
**Session:** Phase 3 DB Persistence + LiteLLM Proxy — Pre-implementation baseline
**Observer:** Observer Full (Sonnet 4.6)
**Status:** BLOCKERS FOUND — Implementation incomplete against contract

---

## Executive Summary

Phase 3 has a partial implementation: `src/silkroute/db/pool.py` is complete and correct, and `db/__init__.py` is properly structured. However, three repository modules are missing, the agent loop has no DB wiring, the router has no proxy mode, and `asyncpg` is absent from `pyproject.toml`. The existing foundation (pool singleton, graceful failure pattern, schema) is architecturally sound. Six specific contract violations are flagged, five of which are BLOCKERs.

---

## Pattern 1: Agent Drift (Scope Violation)

**Status: INFO — no out-of-scope modifications detected**

`git diff --name-only main...HEAD` returned no output (branch is at main). The partial Phase 3 implementation exists as committed code on main. No files outside the contract scope have been modified.

Files that should have been modified/created per contract but are not yet present:

| Contract Deliverable | File | Status |
|---------------------|------|--------|
| Pool singleton | `src/silkroute/db/pool.py` | DONE |
| DB package init | `src/silkroute/db/__init__.py` | DONE |
| Sessions repository | `src/silkroute/db/repositories/sessions.py` | MISSING |
| Cost logs repository | `src/silkroute/db/repositories/cost_logs.py` | MISSING |
| Projects repository | `src/silkroute/db/repositories/projects.py` | MISSING |
| Loop DB integration | `src/silkroute/agent/loop.py` (modified) | NOT STARTED |
| Proxy mode toggle | `src/silkroute/agent/router.py` (modified) | NOT STARTED |
| asyncpg dependency | `pyproject.toml` (modified) | NOT STARTED |
| DB pool tests | `tests/test_db_pool.py` | MISSING |
| Sessions tests | `tests/test_db_sessions.py` | MISSING |
| Cost logs tests | `tests/test_db_cost_logs.py` | MISSING |
| Projects tests | `tests/test_db_projects.py` | MISSING |

---

## Pattern 4: Scope Creep

**Status: PASS**

No out-of-scope features detected in the partial implementation. `pool.py` stays within its mandate: pool singleton, graceful failure, URL masking for logging. The `repositories/__init__.py` is a placeholder only. No budget webhook code, no tool audit log persistence, no dashboard API endpoints — all correctly deferred to later phases.

---

## Pattern 7: Contract Drift

**Status: BLOCKERS FOUND**

### 7a. SessionStatus.BUDGET_EXCEEDED mapping

**Severity: [BLOCKER]**

The contract requires:
> `BUDGET_EXCEEDED` → `'failed'` at DB boundary (DB CHECK constraint only allows: `active`, `completed`, `failed`, `timeout`)

`src/silkroute/agent/session.py:23` defines:
```python
BUDGET_EXCEEDED = "budget_exceeded"
```

`sql/init.sql:81` defines the constraint:
```sql
status TEXT NOT NULL DEFAULT 'active'
    CHECK (status IN ('active', 'completed', 'failed', 'timeout'))
```

The value `"budget_exceeded"` will violate the CHECK constraint if inserted directly. The sessions repository (when written) MUST translate this:

```python
db_status = "failed" if session.status == SessionStatus.BUDGET_EXCEEDED else session.status.value
```

This translation logic does not yet exist because the repository does not yet exist. The risk is that when the repository IS written, the developer forgets this mapping and the DB insert fails silently (or raises, breaking the non-fatal contract).

**Required action:** When `repositories/sessions.py` is implemented, add an explicit mapping function and a test case that verifies `BUDGET_EXCEEDED` is stored as `"failed"`.

### 7b. cost_logs INSERT column mapping

**Severity: [BLOCKER]**

The `cost_logs` table schema (from `sql/init.sql:22-45`) requires these columns:

| Column | Type | Nullable | Notes |
|--------|------|----------|-------|
| `project_id` | TEXT NOT NULL | NO | FK to projects(id) |
| `model_id` | TEXT NOT NULL | NO | From ModelSpec.model_id |
| `model_tier` | TEXT NOT NULL CHECK(...) | NO | 'free' / 'standard' / 'premium' |
| `provider` | TEXT NOT NULL | NO | From ModelSpec.provider.value |
| `input_tokens` | INTEGER NOT NULL | NO | From Iteration.input_tokens |
| `output_tokens` | INTEGER NOT NULL | NO | From Iteration.output_tokens |
| `total_tokens` | INTEGER NOT NULL | NO | input + output (computed) |
| `cost_usd` | NUMERIC(10,6) NOT NULL | NO | From Iteration.cost_usd |
| `task_type` | TEXT | YES | Default 'unknown' |
| `session_id` | TEXT | YES | From AgentSession.id |
| `request_id` | TEXT | YES | Optional |
| `latency_ms` | INTEGER | YES | From Iteration.latency_ms |

The `total_tokens` column requires explicit computation (`input_tokens + output_tokens`). If the repository uses `**dataclass_fields` style insertion it will miss `total_tokens`. The CHECK constraint on `model_tier` must receive lowercase values `'free'`, `'standard'`, or `'premium'` — `ModelTier.STANDARD.value == "standard"` satisfies this.

**Required action:** When `repositories/cost_logs.py` is implemented, explicitly compute `total_tokens` and verify `model_tier` is stored as the `.value` string.

### 7c. agent_sessions INSERT/UPDATE column mapping

**Severity: [WARNING]**

The `agent_sessions` table (from `sql/init.sql:78-94`) defines `messages_json JSONB DEFAULT '[]'`. This column is present in the schema but will likely be omitted from the repository INSERT to avoid storing the full message history (large, sensitive).

If messages are stored, they must be JSON-serialized (the `messages` field is `list[dict]`, which serializes cleanly). The column has a default, so omitting it is safe. But the contract says the repository should perform `AgentSession INSERT/UPDATE/CLOSE` — a decision must be made and documented about whether `messages_json` is populated.

**Required action:** Document in `repositories/sessions.py` whether `messages_json` is populated. If yes, verify it serializes correctly. If no, confirm the default is sufficient.

### 7d. v_budget_remaining view field names

**Severity: [INFO]**

The contract specifies `repositories/projects.py` should query `v_budget_remaining`. The view returns these columns:
```sql
project_id, project_name, budget_monthly_usd, spent_this_month, remaining, status
```

When `projects.py` is written, the return type must use these exact field names. Any Python dataclass or dict using `budget_remaining` instead of `remaining`, or `project` instead of `project_id`, will fail at runtime.

### 7e. _PROXY_MODEL_MAP missing from router.py

**Severity: [BLOCKER]**

The contract requires:
> `_PROXY_MODEL_MAP` mapping 11 model IDs to `silkroute-*` aliases

`src/silkroute/agent/router.py` has no `_PROXY_MODEL_MAP`, no `SILKROUTE_USE_LITELLM_PROXY` env var check, and no `localhost:4000` routing. This entire section is unimplemented.

Cross-referencing `litellm_config.yaml` model_names against `providers/models.py` model IDs, the correct mapping must be:

| model_id (providers/models.py) | litellm alias (litellm_config.yaml) |
|-------------------------------|--------------------------------------|
| `qwen/qwen3-coder:free` | `silkroute-free-coder` |
| `deepseek/deepseek-r1-0528:free` | `silkroute-free-reasoning` |
| `z-ai/glm-4.5-air:free` | `silkroute-free-general` |
| `deepseek/deepseek-v3.2` | `silkroute-standard` |
| `qwen/qwen3-235b-a22b-2507` | `silkroute-standard-fallback` |
| `z-ai/glm-4.7` | `silkroute-standard-tools` |
| `qwen/qwen3-30b-a3b` | `silkroute-standard-light` |
| `deepseek/deepseek-r1-0528` | `silkroute-premium` |
| `qwen/qwen3-coder` | `silkroute-premium-code` |
| `z-ai/glm-5` | `silkroute-premium-agent` |
| `moonshotai/kimi-k2` | `silkroute-premium-multiagent` |

The two local Ollama models (`ollama/qwen3:30b-a3b`, `ollama/glm4:9b`) are correctly excluded — they are commented out in `litellm_config.yaml` and cannot be proxied. The contract says "11 model IDs" which matches the 11 non-Ollama models above.

**Required action:** Implement `_PROXY_MODEL_MAP` in `router.py` using exactly the mapping above. The `get_litellm_model_string()` function must be extended to check `SILKROUTE_USE_LITELLM_PROXY` and return `openai/silkroute-*` (or `silkroute-*`) pointing to `http://localhost:4000`.

### 7f. asyncpg missing from pyproject.toml

**Severity: [BLOCKER]**

`src/silkroute/db/pool.py` imports `asyncpg` at line 9. `pyproject.toml` does not declare `asyncpg` as a dependency. On a clean `pip install silkroute`, the import will fail with `ModuleNotFoundError`.

**Required action:** Add `asyncpg>=0.29.0` to `[project].dependencies` in `pyproject.toml`.

---

## Devil's Advocate Challenges

### Challenge 1: Does pool.py need to be a module-level singleton?

**File:** `src/silkroute/db/pool.py:16` — `_pool: asyncpg.Pool | None = None`

**Concern:** Module-level mutable state is fragile in async contexts. If `get_pool()` is called concurrently before the pool is initialized, two pools could be created (a race condition). The `global _pool` pattern has no locking.

**Severity:** WARNING for production, acceptable for Phase 3 (single-process CLI).

**Alternative:** Use `asyncio.Lock()` to guard pool initialization:
```python
_pool_lock = asyncio.Lock()
async def get_pool():
    async with _pool_lock:
        if _pool is None:
            ...
```

**Assessment:** For a CLI agent running one session at a time, the race is unlikely. Flag for Phase 4 when daemon mode (3 concurrent sessions) is implemented. Log it now.

### Challenge 2: Should `close_pool()` be called, and by whom?

**File:** `src/silkroute/db/pool.py:44` — `close_pool()` exists but nothing calls it

**Concern:** The `pool.py` module exports `close_pool()` but `loop.py` (where DB calls will live) has no cleanup hook. If the CLI exits normally after `run_agent()`, the pool is never closed. asyncpg pools hold open TCP connections — this is a file descriptor leak in long-running processes.

**Alternative:** `loop.py` should call `await close_pool()` in a `finally` block after the agent run, or the CLI layer should call it before exiting.

**Assessment:** Not a blocker for Phase 3 (CLI process exits after one run, OS reclaims connections). Must be addressed in Phase 7 daemon mode. Note in `close_pool` docstring.

### Challenge 3: Is the `_mask_url` function robust enough?

**File:** `src/silkroute/db/pool.py:53-59` — URL masking for safe logging

**Concern:** The URL format assumed is `postgresql://user:password@host:port/db`. If the URL uses the `postgresql://user@host/db` format (no password), the function checks `":" in url.split("@")[0]` which would still be true if there's a port-like pattern in the protocol (`postgresql:`). Let's trace:

For `postgresql://user@localhost:5432/db`:
- `url.split("@")` = `["postgresql://user", "localhost:5432/db"]`
- `prefix = "postgresql://user"`, which contains `:` from `postgresql:`
- `user_part = prefix.rsplit(":", 1)[0]` = `"postgresql"`
- Result: `"postgresql:***@localhost:5432/db"` — INCORRECT masking that would obscure the username

**Alternative:** Use `urllib.parse.urlparse` for robust URL parsing:
```python
from urllib.parse import urlparse, urlunparse
def _mask_url(url: str) -> str:
    p = urlparse(url)
    if p.password:
        masked = p._replace(netloc=f"{p.username}:***@{p.hostname}:{p.port}")
        return urlunparse(masked)
    return url
```

**Assessment:** The default `postgres_url` in `DatabaseConfig` always includes a password (`postgresql://silkroute:silkroute@...`), so the bug only manifests with non-standard URLs. Low risk for Phase 3, but fix before daemon mode where URL configurations are more variable.

### Challenge 4: Is `BUDGET_EXCEEDED → 'failed'` mapping the right semantic?

**File:** `sql/init.sql:81` — CHECK constraint, `session.py:23` — BUDGET_EXCEEDED enum

**Concern:** Storing `BUDGET_EXCEEDED` as `'failed'` loses information. A budget-exceeded session is distinguishable from a true failure (LLM error, exception). Anyone querying `agent_sessions WHERE status = 'failed'` will mix the two event types.

**Alternative 1:** Add `'budget_exceeded'` to the DB CHECK constraint. This is a schema migration, but it's the honest approach.

**Alternative 2:** Store `BUDGET_EXCEEDED` as `'completed'` (the agent completed its run, just without finishing the task).

**Alternative 3:** Add a `terminal_reason TEXT` column to `agent_sessions` for detailed attribution.

**Assessment:** The constraint is correct as-is for Phase 3 (the contract explicitly documents this mapping). However, this is a data quality issue — budget-exceeded sessions will be indistinguishable from crash-failed sessions in analytics. Recommend adding `terminal_reason` column in Phase 3b.

### Challenge 5: Is the `repositories/__init__.py` placeholder sufficient?

**File:** `src/silkroute/db/repositories/__init__.py` — only contains a docstring

**Concern:** The placeholder `__init__.py` suggests the repositories directory is declared but the implementation has not started. `db/__init__.py` imports only `get_pool` and `close_pool` from `pool.py` — once the repositories are created, `db/__init__.py` should also export the repository classes/functions to give callers a single import point.

**Alternative:** Leave `db/__init__.py` minimal (current approach is fine). Callers import from specific modules (`from silkroute.db.repositories.sessions import create_session`). Both patterns are valid; pick one and document it.

**Assessment:** Not a blocker, but the module's public API needs to be decided before writing the repositories.

---

## Contract Compliance

| Contract Requirement | Status | Severity |
|---------------------|--------|----------|
| `db/pool.py` — asyncpg pool singleton | DONE | — |
| `db/__init__.py` — package init | DONE | — |
| `db/repositories/sessions.py` | MISSING | [BLOCKER] |
| `db/repositories/cost_logs.py` | MISSING | [BLOCKER] |
| `db/repositories/projects.py` | MISSING | [BLOCKER] |
| `loop.py` DB wiring | NOT STARTED | [BLOCKER] |
| `router.py` proxy mode + `_PROXY_MODEL_MAP` | NOT STARTED | [BLOCKER] |
| `asyncpg>=0.29.0` in pyproject.toml | MISSING | [BLOCKER] |
| 4 new test files for DB modules | MISSING | [BLOCKER] |
| `BUDGET_EXCEEDED` → `'failed'` mapping | Unverifiable (repository missing) | [BLOCKER] |
| All 65 existing tests still pass | Unverifiable (no run) | — |
| `ruff check` clean | Unverifiable | — |

---

## Monitoring Runs

| Date | Time | Session | Result |
|------|------|---------|--------|
| 2026-02-22 | 01:41 UTC | Phase 3 pre-implementation baseline | BLOCKERS — incomplete implementation |
