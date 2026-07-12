# Local Cost/Model Dashboard Implementation Plan

> **For Claude:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** Add per-model cost/usage visibility (table, API route, dashboard section) reusing silkroute's existing self-hosted Postgres, so government/air-gapped/privacy-conscious deployments get full cost tracking with zero external network dependency.

**Architecture:** Mirror the existing `budget_snapshots` pattern exactly, but grouped by `(project_id, model_id, provider)` instead of just `project_id`/tier. New table `model_cost_snapshots`, new repository file `db/repositories/model_cost_snapshots.py`, new route `GET /budget/models` in the existing `api/routes/budget.py`, new section on the existing dashboard Budget page. No new services, no new datastores — `cost_logs` already captures every run (including free/local Ollama).

**Tech Stack:** Python 3.12, asyncpg, FastAPI, pytest + pytest-asyncio, Next.js 15 / React 19 / TypeScript.

**Design doc:** `docs/plans/2026-07-12-local-cost-dashboard-design.md` (read this first for full context/rationale).

---

### Task 1: Add `model_cost_snapshots` table to the schema

**Files:**
- Modify: `sql/init.sql` (append after the existing `budget_snapshots` table, around line 72)

**Step 1: Add the table definition**

Insert immediately after the `budget_snapshots` table's closing `);` (after line 72, before the `-- Agent Sessions` comment block):

```sql
-- ============================================================
-- Model Cost Snapshots — daily rollups broken out by model
-- ============================================================
CREATE TABLE IF NOT EXISTS model_cost_snapshots (
    id              BIGSERIAL PRIMARY KEY,
    project_id      TEXT NOT NULL REFERENCES projects(id),
    model_id        TEXT NOT NULL,
    provider        TEXT NOT NULL,
    snapshot_date   DATE NOT NULL,
    total_cost_usd  NUMERIC(10, 6) NOT NULL DEFAULT 0.0,
    total_requests  INTEGER NOT NULL DEFAULT 0,
    total_tokens    BIGINT NOT NULL DEFAULT 0,

    created_at      TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    UNIQUE(project_id, model_id, provider, snapshot_date)
);

CREATE INDEX IF NOT EXISTS idx_model_cost_snapshots_project ON model_cost_snapshots(project_id);
CREATE INDEX IF NOT EXISTS idx_model_cost_snapshots_model ON model_cost_snapshots(model_id);
```

Note: uses `BIGSERIAL id PRIMARY KEY` + `UNIQUE(...)` rather than a composite primary key, matching `budget_snapshots`'s exact convention (not the composite-PK sketch in the design doc — this implementation plan is the source of truth).

**Step 2: Verify the file is still valid SQL**

Run: `psql --version` (just confirm psql is available; we're not running this against a live DB yet — Task 6 covers that).

There's no automated test for `init.sql` directly — correctness is verified in Task 6 when the schema is actually applied.

**Step 3: Commit**

```bash
git add sql/init.sql
git commit -m "feat(db): add model_cost_snapshots table for per-model cost tracking"
```

---

### Task 2: Repository layer — `rollup_day()` and `get_snapshots()`

**Files:**
- Create: `src/silkroute/db/repositories/model_cost_snapshots.py`
- Test: `tests/test_model_cost_snapshots.py`

**Step 1: Write the failing tests**

Create `tests/test_model_cost_snapshots.py` — this mirrors `tests/test_budget_snapshots.py` exactly, swapping the tier-grouping assertions for model/provider-grouping ones (no `backfill()` in v1 — not needed, `budget_snapshots.backfill()` already exists as the pattern if ever wanted later):

```python
"""Tests for db/repositories/model_cost_snapshots.py — per-model daily rollup."""

from __future__ import annotations

import datetime
from unittest.mock import AsyncMock

import pytest

from silkroute.db.repositories.model_cost_snapshots import (
    get_snapshots,
    rollup_day,
)


@pytest.fixture
def mock_pool() -> AsyncMock:
    return AsyncMock()


class TestRollupDay:
    async def test_calls_pool_execute(self, mock_pool: AsyncMock) -> None:
        date = datetime.date(2026, 3, 1)
        await rollup_day(mock_pool, date)
        mock_pool.execute.assert_awaited_once()

    async def test_passes_date_as_first_positional_arg(self, mock_pool: AsyncMock) -> None:
        date = datetime.date(2026, 3, 1)
        await rollup_day(mock_pool, date)
        args = mock_pool.execute.call_args[0]
        assert args[1] == date

    async def test_sql_contains_insert_into_model_cost_snapshots(
        self, mock_pool: AsyncMock
    ) -> None:
        date = datetime.date(2026, 3, 1)
        await rollup_day(mock_pool, date)
        sql = mock_pool.execute.call_args[0][0]
        assert "INSERT INTO model_cost_snapshots" in sql

    async def test_sql_contains_on_conflict_upsert(self, mock_pool: AsyncMock) -> None:
        date = datetime.date(2026, 3, 1)
        await rollup_day(mock_pool, date)
        sql = mock_pool.execute.call_args[0][0]
        assert "ON CONFLICT" in sql
        assert "DO UPDATE SET" in sql

    async def test_sql_contains_cost_logs_source(self, mock_pool: AsyncMock) -> None:
        date = datetime.date(2026, 3, 1)
        await rollup_day(mock_pool, date)
        sql = mock_pool.execute.call_args[0][0]
        assert "FROM cost_logs" in sql

    async def test_sql_contains_group_by_model_and_provider(
        self, mock_pool: AsyncMock
    ) -> None:
        date = datetime.date(2026, 3, 1)
        await rollup_day(mock_pool, date)
        sql = mock_pool.execute.call_args[0][0]
        assert "GROUP BY project_id, model_id, provider" in sql

    async def test_idempotent_upsert_updates_all_columns(
        self, mock_pool: AsyncMock
    ) -> None:
        date = datetime.date(2026, 3, 1)
        await rollup_day(mock_pool, date)
        sql = mock_pool.execute.call_args[0][0]
        assert "total_cost_usd = EXCLUDED.total_cost_usd" in sql
        assert "total_requests = EXCLUDED.total_requests" in sql
        assert "total_tokens = EXCLUDED.total_tokens" in sql


class TestGetSnapshots:
    async def test_returns_list_of_dicts(self, mock_pool: AsyncMock) -> None:
        mock_pool.fetch.return_value = [
            {
                "id": 1,
                "project_id": "proj-1",
                "model_id": "ollama/qwen2.5:14b",
                "provider": "ollama",
                "snapshot_date": datetime.date(2026, 3, 1),
                "total_cost_usd": 0.0,
                "total_requests": 7,
                "total_tokens": 23029,
            }
        ]
        result = await get_snapshots(
            mock_pool,
            "proj-1",
            datetime.date(2026, 3, 1),
            datetime.date(2026, 3, 7),
        )
        assert len(result) == 1
        assert result[0]["model_id"] == "ollama/qwen2.5:14b"

    async def test_returns_empty_list_when_no_rows(self, mock_pool: AsyncMock) -> None:
        mock_pool.fetch.return_value = []
        result = await get_snapshots(
            mock_pool,
            "proj-missing",
            datetime.date(2026, 1, 1),
            datetime.date(2026, 1, 31),
        )
        assert result == []

    async def test_passes_project_id_and_dates_as_params(
        self, mock_pool: AsyncMock
    ) -> None:
        mock_pool.fetch.return_value = []
        start = datetime.date(2026, 2, 1)
        end = datetime.date(2026, 2, 28)
        await get_snapshots(mock_pool, "proj-abc", start, end)
        args = mock_pool.fetch.call_args[0]
        assert args[1] == "proj-abc"
        assert args[2] == start
        assert args[3] == end

    async def test_sql_contains_date_range_filter(self, mock_pool: AsyncMock) -> None:
        mock_pool.fetch.return_value = []
        await get_snapshots(
            mock_pool,
            "proj-1",
            datetime.date(2026, 3, 1),
            datetime.date(2026, 3, 7),
        )
        sql = mock_pool.fetch.call_args[0][0]
        assert "snapshot_date >=" in sql
        assert "snapshot_date <=" in sql

    async def test_sql_orders_by_snapshot_date_asc(self, mock_pool: AsyncMock) -> None:
        mock_pool.fetch.return_value = []
        await get_snapshots(
            mock_pool,
            "proj-1",
            datetime.date(2026, 3, 1),
            datetime.date(2026, 3, 7),
        )
        sql = mock_pool.fetch.call_args[0][0]
        assert "ORDER BY snapshot_date ASC" in sql
```

**Step 2: Run tests to verify they fail**

Run: `source .venv/bin/activate && pytest tests/test_model_cost_snapshots.py -v`
Expected: FAIL / collection error — `ModuleNotFoundError: No module named 'silkroute.db.repositories.model_cost_snapshots'`

**Step 3: Write the implementation**

Create `src/silkroute/db/repositories/model_cost_snapshots.py`:

```python
"""Model cost snapshot rollup persistence — UPSERT and query for
model_cost_snapshots table.

Follows the pool-based function pattern established by budget_snapshots.py,
but grouped by (project_id, model_id, provider) instead of just project_id/tier
— this is the per-model view budget_snapshots deliberately doesn't provide.
"""

from __future__ import annotations

import datetime
from typing import Any

import asyncpg
import structlog

log = structlog.get_logger()


async def rollup_day(pool: asyncpg.Pool, date: datetime.date) -> None:
    """UPSERT a daily per-model rollup for all projects for the given date.

    Aggregates cost_logs rows for the given calendar day, grouped by
    project_id, model_id, and provider, and upserts into
    model_cost_snapshots. Safe to call multiple times — idempotent.
    """
    await pool.execute(
        """
        INSERT INTO model_cost_snapshots (
            project_id, model_id, provider, snapshot_date,
            total_cost_usd, total_requests, total_tokens
        )
        SELECT
            project_id,
            model_id,
            provider,
            $1::date,
            SUM(cost_usd),
            COUNT(*),
            SUM(total_tokens)
        FROM cost_logs
        WHERE created_at >= $1::date AND created_at < $1::date + INTERVAL '1 day'
        GROUP BY project_id, model_id, provider
        ON CONFLICT (project_id, model_id, provider, snapshot_date) DO UPDATE SET
            total_cost_usd = EXCLUDED.total_cost_usd,
            total_requests = EXCLUDED.total_requests,
            total_tokens = EXCLUDED.total_tokens
        """,
        date,
    )
    log.debug("db_model_cost_snapshot_rolled_up", date=str(date))


async def get_snapshots(
    pool: asyncpg.Pool,
    project_id: str,
    start_date: datetime.date,
    end_date: datetime.date,
) -> list[dict[str, Any]]:
    """SELECT per-model cost snapshots for a project within [start_date, end_date]."""
    rows = await pool.fetch(
        """
        SELECT *
        FROM model_cost_snapshots
        WHERE project_id = $1
          AND snapshot_date >= $2
          AND snapshot_date <= $3
        ORDER BY snapshot_date ASC
        """,
        project_id,
        start_date,
        end_date,
    )
    return [dict(r) for r in rows]
```

**Step 4: Run tests to verify they pass**

Run: `source .venv/bin/activate && pytest tests/test_model_cost_snapshots.py -v`
Expected: PASS — all tests green.

**Step 5: Lint**

Run: `ruff check src/silkroute/db/repositories/model_cost_snapshots.py tests/test_model_cost_snapshots.py`
Expected: no errors.

**Step 6: Commit**

```bash
git add src/silkroute/db/repositories/model_cost_snapshots.py tests/test_model_cost_snapshots.py
git commit -m "feat(db): add model_cost_snapshots repository (rollup_day, get_snapshots)"
```

---

### Task 3: API layer — `GET /budget/models`

**Files:**
- Modify: `src/silkroute/api/models.py` (add Pydantic response models near `BudgetSnapshotItem`/`BudgetSnapshotListResponse`)
- Modify: `src/silkroute/api/routes/budget.py`
- Test: Create `tests/test_api_budget_models.py`

**Step 1: Write the failing tests**

Create `tests/test_api_budget_models.py`, following the exact `TestClient` + dependency-override pattern used in `tests/test_api_projects.py`:

```python
"""Tests for GET /budget/models — per-model cost breakdown endpoint."""

from __future__ import annotations

import datetime
from unittest.mock import AsyncMock, patch

import fakeredis.aioredis
import pytest
from fastapi.testclient import TestClient

from silkroute.api.app import create_app
from silkroute.api.deps import get_redis
from silkroute.config.settings import SilkRouteSettings
from silkroute.daemon.queue import TaskQueue


@pytest.fixture
def fake_redis_client() -> fakeredis.aioredis.FakeRedis:
    return fakeredis.aioredis.FakeRedis(decode_responses=True)


@pytest.fixture
def mock_db_pool() -> AsyncMock:
    return AsyncMock()


@pytest.fixture
def app(
    test_settings: SilkRouteSettings,
    fake_redis_client: fakeredis.aioredis.FakeRedis,
    mock_db_pool: AsyncMock,
) -> TestClient:
    application = create_app(settings=test_settings)
    queue = TaskQueue(fake_redis_client, maxsize=100)
    application.state.redis = fake_redis_client
    application.state.queue = queue
    application.state.db_pool = mock_db_pool

    application.dependency_overrides[get_redis] = lambda: fake_redis_client

    return TestClient(application, raise_server_exceptions=False)


AUTH = {"Authorization": "Bearer test-secret"}


class TestBudgetModelsRoute:
    def test_route_not_shadowed_by_project_id_route(self, app: TestClient) -> None:
        """/budget/models must not be captured by the /budget/{project_id} route.

        Regression guard for the route-ordering rule already established in
        this codebase: list/static routes must be declared before parameterized
        ones in the same router, or FastAPI matches the wrong one first.
        """
        with patch(
            "silkroute.db.repositories.model_cost_snapshots.get_snapshots",
            new=AsyncMock(return_value=[]),
        ):
            response = app.get(
                "/budget/models?project_id=test-proj", headers=AUTH
            )
        assert response.status_code == 200
        # If shadowed by /budget/{project_id}, the response would be a
        # ProjectBudgetResponse shape (has "monthly_spent_usd"), not our
        # list shape (has "snapshots").
        assert "snapshots" in response.json()

    def test_returns_empty_list_when_no_db_pool(self, app: TestClient) -> None:
        app.app.state.db_pool = None
        response = app.get("/budget/models?project_id=test-proj", headers=AUTH)
        assert response.status_code == 200
        assert response.json() == {"snapshots": [], "count": 0}

    def test_returns_snapshots_from_repository(self, app: TestClient) -> None:
        fake_row = {
            "project_id": "test-proj",
            "model_id": "ollama/qwen2.5:14b",
            "provider": "ollama",
            "snapshot_date": datetime.date(2026, 3, 1),
            "total_cost_usd": 0.0,
            "total_requests": 7,
            "total_tokens": 23029,
        }
        with patch(
            "silkroute.db.repositories.model_cost_snapshots.get_snapshots",
            new=AsyncMock(return_value=[fake_row]),
        ):
            response = app.get(
                "/budget/models?project_id=test-proj", headers=AUTH
            )
        assert response.status_code == 200
        body = response.json()
        assert body["count"] == 1
        assert body["snapshots"][0]["model_id"] == "ollama/qwen2.5:14b"

    def test_fails_open_on_repository_error(self, app: TestClient) -> None:
        with patch(
            "silkroute.db.repositories.model_cost_snapshots.get_snapshots",
            new=AsyncMock(side_effect=RuntimeError("db down")),
        ):
            response = app.get(
                "/budget/models?project_id=test-proj", headers=AUTH
            )
        assert response.status_code == 200
        assert response.json() == {"snapshots": [], "count": 0}
```

**Step 2: Run tests to verify they fail**

Run: `source .venv/bin/activate && pytest tests/test_api_budget_models.py -v`
Expected: FAIL — 404 or `AttributeError`, since the route and Pydantic models don't exist yet.

**Step 3: Add the Pydantic response models**

In `src/silkroute/api/models.py`, add immediately after the existing `BudgetSnapshotListResponse` class:

```python
class ModelCostSnapshotItem(BaseModel):
    """A single daily per-model cost snapshot for a project."""

    project_id: str
    model_id: str
    provider: str
    snapshot_date: str
    total_cost_usd: float
    total_requests: int
    total_tokens: int


class ModelCostSnapshotListResponse(BaseModel):
    """GET /budget/models response."""

    snapshots: list[ModelCostSnapshotItem]
    count: int
```

**Step 4: Add the route**

In `src/silkroute/api/routes/budget.py`:

1. Update the import block to include the new models:

```python
from silkroute.api.models import (
    BudgetSnapshotItem,
    BudgetSnapshotListResponse,
    GlobalBudgetResponse,
    ModelCostSnapshotItem,
    ModelCostSnapshotListResponse,
    ProjectBudgetResponse,
)
```

2. Add the new route **immediately after the existing `/snapshots` route and before `/{project_id}`** (critical — this is the route-ordering rule from the design doc; placing it after `/{project_id}` would make it unreachable):

```python
@router.get("/models")
async def budget_models(
    project_id: str = Query(..., description="Project ID to fetch per-model costs for"),
    start_date: datetime.date = Query(
        default=datetime.date.today() - datetime.timedelta(days=30),
        description="Inclusive start date (YYYY-MM-DD)",
    ),
    end_date: datetime.date = Query(
        default=datetime.date.today(),
        description="Inclusive end date (YYYY-MM-DD)",
    ),
    db_pool: asyncpg.Pool | None = Depends(get_db_pool),
) -> ModelCostSnapshotListResponse:
    """Get daily per-model cost breakdown for a project.

    Fails open if Postgres is unavailable — returns an empty list.
    """
    if db_pool is None:
        return ModelCostSnapshotListResponse(snapshots=[], count=0)

    try:
        from silkroute.db.repositories.model_cost_snapshots import get_snapshots

        rows = await get_snapshots(db_pool, project_id, start_date, end_date)
    except Exception:
        return ModelCostSnapshotListResponse(snapshots=[], count=0)

    items = [
        ModelCostSnapshotItem(
            project_id=str(row["project_id"]),
            model_id=str(row["model_id"]),
            provider=str(row["provider"]),
            snapshot_date=str(row["snapshot_date"]),
            total_cost_usd=float(row["total_cost_usd"]),
            total_requests=int(row["total_requests"]),
            total_tokens=int(row["total_tokens"]),
        )
        for row in rows
    ]
    return ModelCostSnapshotListResponse(snapshots=items, count=len(items))
```

Confirm final route order in the file is: `""` (global), `/snapshots`, `/models`, `/{project_id}` — the two static routes before the parameterized one.

**Step 5: Run tests to verify they pass**

Run: `source .venv/bin/activate && pytest tests/test_api_budget_models.py -v`
Expected: PASS — all 4 tests green.

**Step 6: Run the full test suite to check for regressions**

Run: `source .venv/bin/activate && pytest -q`
Expected: all tests pass (929 + new tests, no regressions in existing budget routes).

**Step 7: Lint**

Run: `ruff check src/silkroute/api/models.py src/silkroute/api/routes/budget.py tests/test_api_budget_models.py`
Expected: no errors.

**Step 8: Commit**

```bash
git add src/silkroute/api/models.py src/silkroute/api/routes/budget.py tests/test_api_budget_models.py
git commit -m "feat(api): add GET /budget/models per-model cost endpoint"
```

---

### Task 4: Wire the rollup into the existing scheduler

**Files:**
- Modify: `src/silkroute/daemon/scheduler.py`
- Modify: `tests/test_daemon_scheduler.py`

**Step 1: Read the existing `_budget_rollup` test(s) to find the right spot**

Run: `grep -n "_budget_rollup\|budget_rollup" tests/test_daemon_scheduler.py`

If a test already calls/asserts on `_budget_rollup`, add a new assertion alongside it in Step 3 below rather than duplicating the whole test — match whatever fixture/mocking pattern that file already uses for `self._db_pool` and `rollup_day`.

**Step 2: Write the failing test**

Add to `tests/test_daemon_scheduler.py` (adjust fixture names to match whatever this file already uses for `scheduler`/`_db_pool` mocks — mirror the existing budget-rollup test's setup exactly):

```python
async def test_budget_rollup_also_rolls_up_model_costs(self, ...) -> None:
    """_budget_rollup must roll up both budget_snapshots and model_cost_snapshots."""
    with patch(
        "silkroute.db.repositories.model_cost_snapshots.rollup_day",
        new_callable=AsyncMock,
    ) as mock_model_rollup:
        await scheduler._budget_rollup()
        mock_model_rollup.assert_awaited_once()
```

**Step 3: Run test to verify it fails**

Run: `source .venv/bin/activate && pytest tests/test_daemon_scheduler.py -k model_cost -v`
Expected: FAIL — `model_cost_snapshots.rollup_day` never called.

**Step 4: Update `_budget_rollup`**

In `src/silkroute/daemon/scheduler.py`, modify `_budget_rollup` (around line 169-178):

```python
    async def _budget_rollup(self) -> None:
        """Roll up yesterday's cost_logs into budget_snapshots and model_cost_snapshots."""
        import datetime

        from silkroute.db.repositories.budget_snapshots import rollup_day
        from silkroute.db.repositories.model_cost_snapshots import (
            rollup_day as rollup_model_costs_day,
        )

        yesterday = datetime.date.today() - datetime.timedelta(days=1)
        log.info("scheduler_budget_rollup_triggered", date=str(yesterday))
        await rollup_day(self._db_pool, yesterday)
        await rollup_model_costs_day(self._db_pool, yesterday)
        log.info("scheduler_budget_rollup_done", date=str(yesterday))
```

Don't rename the job/method (`_budget_rollup`, job id `"budget_rollup"`) — it stays the single daily cron tick doing both rollups, per the design doc's explicit decision not to invent a second schedule.

**Step 5: Run tests to verify they pass**

Run: `source .venv/bin/activate && pytest tests/test_daemon_scheduler.py -v`
Expected: PASS — all tests green, including the new one.

**Step 6: Full suite + lint**

Run: `source .venv/bin/activate && pytest -q && ruff check src/silkroute/daemon/scheduler.py tests/test_daemon_scheduler.py`
Expected: all pass, no lint errors.

**Step 7: Commit**

```bash
git add src/silkroute/daemon/scheduler.py tests/test_daemon_scheduler.py
git commit -m "feat(daemon): roll up model_cost_snapshots alongside budget_snapshots"
```

---

### Task 5: Dashboard — fetch function, type, and Budget page section

**Files:**
- Modify: `dashboard/src/lib/types.ts`
- Modify: `dashboard/src/lib/api.ts`
- Modify: `dashboard/src/app/budget/page.tsx`

There's no existing test runner for the dashboard beyond `npm run lint` (confirmed — no `.test.`/`.spec.` files exist anywhere in `dashboard/`), so this task is verified via lint + build + manual visual check (Task 6), not TDD.

**Step 1: Add the response type**

In `dashboard/src/lib/types.ts`, add after `ProjectBudgetResponse`:

```typescript
export interface ModelCostSnapshotItem {
  project_id: string;
  model_id: string;
  provider: string;
  snapshot_date: string;
  total_cost_usd: number;
  total_requests: number;
  total_tokens: number;
}

export interface ModelCostSnapshotListResponse {
  snapshots: ModelCostSnapshotItem[];
  count: number;
}
```

**Step 2: Add the fetch function**

In `dashboard/src/lib/api.ts`:

1. Add `ModelCostSnapshotListResponse` to the top-of-file type import.
2. Add after `fetchProjectBudget`:

```typescript
export async function fetchModelCosts(
  projectId: string,
  startDate?: string,
  endDate?: string
): Promise<ModelCostSnapshotListResponse> {
  const params = new URLSearchParams({ project_id: projectId });
  if (startDate) params.set("start_date", startDate);
  if (endDate) params.set("end_date", endDate);
  return apiFetch<ModelCostSnapshotListResponse>(`/budget/models?${params}`);
}
```

**Step 3: Add the dashboard section**

In `dashboard/src/app/budget/page.tsx`:

1. Update imports at the top:

```typescript
import { fetchProjects, fetchProjectBudget, fetchModelCosts } from "@/lib/api";
import type { BudgetSnapshot, ModelCostSnapshotItem } from "@/lib/types";
```

2. Add a new data-fetching function (mirrors `getBudgets()`'s fail-open pattern — empty array on any error, never throws):

```typescript
async function getModelCosts(projectIds: string[]): Promise<ModelCostSnapshotItem[]> {
  try {
    const results = await Promise.all(
      projectIds.map((id) => fetchModelCosts(id).catch(() => ({ snapshots: [], count: 0 })))
    );
    return results.flatMap((r) => r.snapshots);
  } catch {
    return [];
  }
}
```

3. In the `BudgetPage` component, after `const budgets = await getBudgets();`, add:

```typescript
  const modelCosts = await getModelCosts(budgets.map((b) => b.projectId));

  // Aggregate across all projects/dates for a simple per-model total view
  const byModel = new Map<string, { provider: string; cost: number; requests: number; tokens: number }>();
  for (const row of modelCosts) {
    const existing = byModel.get(row.model_id) ?? { provider: row.provider, cost: 0, requests: 0, tokens: 0 };
    existing.cost += row.total_cost_usd;
    existing.requests += row.total_requests;
    existing.tokens += row.total_tokens;
    byModel.set(row.model_id, existing);
  }
  const modelRows = Array.from(byModel.entries()).sort((a, b) => b[1].cost - a[1].cost);
```

4. Add a new section in the JSX, after the closing `</div>` of the "Project Table" block and before "Alert Thresholds":

```tsx
      {/* Cost by Model */}
      <div className="mt-8 bg-neutral-900 border border-neutral-800 rounded-xl overflow-hidden">
        <div className="p-6 pb-0">
          <h2 className="text-lg font-semibold">Cost by Model</h2>
          <p className="text-neutral-500 text-sm mt-1 mb-4">Last 30 days, across all projects.</p>
        </div>
        {modelRows.length === 0 ? (
          <p className="text-neutral-500 text-sm p-6 pt-0">No model usage recorded yet.</p>
        ) : (
          <table className="w-full">
            <thead>
              <tr className="border-b border-neutral-800 text-xs text-neutral-500 uppercase tracking-wider">
                <th className="text-left p-4">Model</th>
                <th className="text-left p-4">Provider</th>
                <th className="text-right p-4">Requests</th>
                <th className="text-right p-4">Tokens</th>
                <th className="text-right p-4">Cost</th>
              </tr>
            </thead>
            <tbody>
              {modelRows.map(([modelId, row]) => (
                <tr key={modelId} className="border-b border-neutral-800/50 hover:bg-neutral-800/30">
                  <td className="p-4 font-medium font-mono text-sm">{modelId}</td>
                  <td className="p-4 text-neutral-400 text-sm">{row.provider}</td>
                  <td className="p-4 text-right font-mono text-sm">{row.requests}</td>
                  <td className="p-4 text-right font-mono text-sm">{row.tokens.toLocaleString()}</td>
                  <td className="p-4 text-right font-mono text-sm">${row.cost.toFixed(4)}</td>
                </tr>
              ))}
            </tbody>
          </table>
        )}
      </div>
```

**Step 4: Lint**

Run: `cd dashboard && npm run lint`
Expected: no errors.

**Step 5: Build**

Run: `cd dashboard && npm run build`
Expected: clean build, no type errors.

**Step 6: Commit**

```bash
git add dashboard/src/lib/types.ts dashboard/src/lib/api.ts dashboard/src/app/budget/page.tsx
git commit -m "feat(dashboard): add Cost by Model section to Budget page"
```

---

### Task 6: End-to-end manual verification

**Files:** none (verification only)

**Step 1: Apply the schema**

Against a real local Postgres (e.g. via `docker compose up -d postgres`, or whatever instance the `.venv` is configured to reach):

Run: `psql "$SILKROUTE_DB_POSTGRES_URL" -f sql/init.sql`
Expected: no errors; `model_cost_snapshots` table now exists alongside the others.

**Step 1.5: Confirm Postgres is actually reachable — DA-review finding, don't skip this**

`persist_sessions` defaults to `True` (`config/settings.py:121`), but `db/pool.py`'s
`get_pool()` silently returns `None` if Postgres isn't reachable when the process starts
(`agent/loop.py:107-116` catches the failure and just logs `db_init_skipped` — no error
surfaced to the console). This means running the demo without confirming Postgres is up first
can silently produce zero `cost_logs` rows, making Step 3's "verification" meaningless (an
empty rollup of an empty table "succeeds" too).

Run:
```bash
docker compose up -d postgres   # if not already running
psql "$SILKROUTE_DB_POSTGRES_URL" -c "SELECT 1"
```
Expected: `SELECT 1` returns `1` with no connection error. Also confirm
`SILKROUTE_DB_POSTGRES_URL` is exported in the *same shell* that will run the demo in Step 2 —
`get_pool()` reads it via `DatabaseConfig`, and a value set in a different shell/session won't
be visible.

**Step 2: Populate real cost_logs rows**

Run the AV demo a few times to generate real local-Ollama iteration data (as already verified working in a prior session):

Run: `python demo/agent_ready_av_demo.py --mock-pearl` (repeat 2-3 times)
Expected: each run completes without a `db_init_skipped` warning in its log output.

**Then verify rows actually landed — do not proceed on assumption:**

Run: `psql "$SILKROUTE_DB_POSTGRES_URL" -c "SELECT count(*) FROM cost_logs;"`
Expected: a nonzero count. **If zero:** stop here and investigate (check the demo's log
output for `db_init_skipped`, re-verify Step 1.5's connectivity check, confirm the env var is
set in the right shell) before moving on to Step 3 — a Step 3 "success" against an empty
table proves nothing.

**Step 3: Trigger the rollup manually**

Rather than waiting for the cron, call it directly to verify the SQL is correct against a real Postgres:

Run:
```bash
python -c "
import asyncio, asyncpg, datetime
from silkroute.db.repositories.model_cost_snapshots import rollup_day

async def main():
    pool = await asyncpg.create_pool('<your SILKROUTE_DB_POSTGRES_URL>')
    await rollup_day(pool, datetime.date.today())
    await pool.close()

asyncio.run(main())
"
```
Expected: no errors; `SELECT * FROM model_cost_snapshots;` in `psql` shows real rows.

**Step 4: Hit the API directly**

Run: `curl -H "Authorization: Bearer $SILKROUTE_API_KEY" "http://localhost:8787/budget/models?project_id=default"`
Expected: JSON response with real `snapshots` data matching what's in the table.

**Step 5: Verify the dashboard renders it**

Run: `cd dashboard && npm run dev`, open `http://localhost:3000/budget`
Expected: "Cost by Model" section shows the real rows from Step 3-4, correctly sorted by cost descending.

**Step 6: Update project docs**

- `.claude/PROJECT_CONTEXT.md`: move this from "Tomorrow" to "Done", note it's live.
- `.claude/Backlog.md`: add a line confirming the local cost dashboard shipped and works end-to-end.

**Step 7: Final commit**

```bash
git add .claude/PROJECT_CONTEXT.md .claude/Backlog.md
git commit -m "docs: local cost dashboard verified end-to-end"
```

---

## Merging back

Once all 6 tasks are done and verified, use `superpowers:finishing-a-development-branch` to decide how to integrate `feature/local-cost-dashboard` back into `main` (merge, PR, or otherwise) — don't merge automatically as part of this plan.
