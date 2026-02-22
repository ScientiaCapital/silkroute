# Feature Contract: Phase 3 — PostgreSQL Persistence + LiteLLM Proxy

**Created**: 2026-02-21
**Scope**: STANDARD (9 new files, 7 modified, 1 new explicit dependency)
**Observer Required**: observer-full (Sonnet 4.6)

## Deliverables

### DB Persistence Layer (`src/silkroute/db/`)
- `pool.py` — asyncpg connection pool singleton (lazy-init, non-fatal)
- `repositories/sessions.py` — AgentSession INSERT/UPDATE/CLOSE
- `repositories/cost_logs.py` — Per-iteration cost log INSERT
- `repositories/projects.py` — Project budget lookup from DB

### Agent Integration (`src/silkroute/agent/`)
- `loop.py` — Wire DB calls at session create, per-iteration, and session close
- All DB operations are try/except wrapped — agent runs without Postgres

### LiteLLM Proxy Mode (`src/silkroute/agent/router.py`)
- `_PROXY_MODEL_MAP` mapping 11 model IDs to `silkroute-*` aliases
- Toggle via `SILKROUTE_USE_LITELLM_PROXY=true` env var
- Routes through `localhost:4000` when enabled

### Tests
- 4 new test files for DB modules (mocked asyncpg, no live DB)
- Extended `test_loop.py` and `test_router.py` for new functionality

## Scope Boundaries

### IN SCOPE
- asyncpg pool singleton with graceful failure
- Session persistence (create, update, close)
- Cost log insertion per iteration
- Project budget query from v_budget_remaining view
- LiteLLM proxy mode toggle
- Unit tests with AsyncMock (no real DB)
- Explicit asyncpg dependency in pyproject.toml

### OUT OF SCOPE
- Budget alert webhooks (Phase 4)
- Tool audit log persistence (Phase 3b)
- Budget snapshot daily rollups (Phase 3b)
- Dashboard API integration (Phase 3b)
- Live DB integration tests (optional @pytest.mark.integration)

## Critical Mappings

### SessionStatus → DB CHECK Constraint
| Python Status | DB Value | Notes |
|--------------|----------|-------|
| ACTIVE | 'active' | Direct |
| COMPLETED | 'completed' | Direct |
| FAILED | 'failed' | Direct |
| TIMEOUT | 'timeout' | Direct |
| BUDGET_EXCEEDED | 'failed' | Mapped — DB CHECK only allows 4 values |

## Observer Checkpoints
- [ ] Architecture Observer approves contract before coding
- [ ] Code Quality Observer runs after each task merge
- [ ] Final Observer report before security gate

## Success Criteria
- [ ] All existing 65 tests still pass
- [ ] New DB tests pass with mocked asyncpg
- [ ] Agent runs normally without Postgres (graceful degradation)
- [ ] Proxy mode correctly maps all 11 models
- [ ] ruff check clean
- [ ] gitleaks clean
- [ ] 0 observer BLOCKERs
