# Local Cost/Telemetry Dashboard — Design

**Date**: 2026-07-12
**Status**: Design validated, implementation not yet started

## Context

For government/courts/military (and privacy-conscious individual) deployments, SilkRoute
needs a cost/usage tracking + dashboard story with zero external network dependency —
phoning home to any cloud SaaS (like `model-finops`'s current Supabase dependency) is
disqualifying for that audience. This came out of investigating why a planned live
model-finops + Supabase telemetry test was blocked: no Supabase project existed, and standing
one up felt like the wrong direction anyway once we looked closer.

Investigation found the real gap is much smaller than "build a new local telemetry system":
**silkroute's own self-hosted Postgres already captures every single agent-loop iteration —
including free/local Ollama runs — into a `cost_logs` table** with `project_id`, `model_id`,
`provider`, tokens, and `cost_usd` (`src/silkroute/agent/loop.py:550-556` →
`db/repositories/cost_logs.py`'s `insert_cost_log`). Zero cloud dependency already, today.
The only thing missing is a per-model aggregation/view — the existing `budget_snapshots`
rollup only groups by tier (free/standard/premium), not by individual model. This design
closes that one gap with a small, additive change reusing every existing pattern in the
codebase — no new datastore, no new service.

This was brainstormed conversationally and validated section-by-section with the user.
Confirmed requirements: v1 targets a single local machine/operator (not multi-user LAN),
extends the existing Next.js `dashboard/` (not a standalone viewer), and "truly local" means
self-hosted infra the user controls is fine (a Postgres container is not disqualifying —
only cloud SaaS is).

## Design

### 1. Data layer — new table + repository file

Add to `sql/init.sql` (idempotent `CREATE TABLE IF NOT EXISTS`, consistent with how every
other table here is created/updated — `scripts/start.sh` just re-runs the whole file on every
startup, no separate migration mechanism exists in this repo):

```sql
CREATE TABLE IF NOT EXISTS model_cost_snapshots (
    project_id      TEXT NOT NULL REFERENCES projects(id),
    model_id        TEXT NOT NULL,
    provider        TEXT NOT NULL,
    snapshot_date   DATE NOT NULL,
    total_cost_usd  NUMERIC NOT NULL DEFAULT 0,
    total_requests  INT NOT NULL DEFAULT 0,
    total_tokens    BIGINT NOT NULL DEFAULT 0,
    PRIMARY KEY (project_id, model_id, provider, snapshot_date)
);
```

New file `src/silkroute/db/repositories/model_cost_snapshots.py`, mirroring
`db/repositories/budget_snapshots.py` exactly (same pool-based function signatures, same
idempotent UPSERT-on-conflict pattern):

- `rollup_day(pool, date)` — UPSERTs from `cost_logs`, grouped by
  `project_id, model_id, provider` instead of just `project_id`/tier.
- `get_snapshots(pool, project_id, start_date, end_date)` — reader, same shape as
  `budget_snapshots.get_snapshots()`.
- No `avg_latency_ms` for v1 (deliberately deferred — can be added later as just another
  column + backfill, data's already in `cost_logs` if wanted).

Wire the new `rollup_day()` into whatever already triggers `budget_snapshots.rollup_day()`
today (scheduler cron at 00:05 UTC, per Phase 7) — call both from the same tick, don't invent
a second schedule.

### 2. API layer — new route

In the existing `src/silkroute/api/routes/budget.py` (keep all cost-related routes in one
file): `GET /budget/models?project_id=&start_date=&end_date=`, returning a list of
`{model_id, provider, snapshot_date, total_cost_usd, total_requests, total_tokens}` — new
Pydantic `ModelCostSnapshotItem`/`ModelCostSnapshotListResponse`, mirroring the existing
`BudgetSnapshotItem`/`BudgetSnapshotListResponse`. Same fail-open behavior as the rest of
`budget.py` (Postgres unreachable → empty list, never a 500).

**Route-ordering gotcha (confirmed real, bit this project before per its own conventions):**
`/budget/{project_id}` already exists as a parameterized route in this file. `/budget/models`
**must** be declared before it, or FastAPI matches `/budget/models` against `{project_id}`
first (`project_id="models"`) and the new route is unreachable.

### 3. Dashboard layer

- `dashboard/src/lib/api.ts`: new `fetchModelCosts(projectId, startDate, endDate)`, mirroring
  `fetchProjectBudget()` exactly — same `apiFetch<T>()` helper, same `NEXT_PUBLIC_API_URL`
  base, same 30s ISR-style revalidation.
- `dashboard/src/lib/types.ts`: new `ModelCostSnapshot` type matching the API response.
- **Render location: extend the existing Budget page** (`dashboard/src/app/budget/page.tsx`)
  — add a "Cost by Model" table below the existing tier-summary cards. Keeps all cost-related
  UI in one place, consistent with the API living under `/budget`.

### 4. Disposition of model-finops

No code changes to `src/silkroute/integrations/finops_client.py` — it stays exactly as-is,
opt-in via `SILKROUTE_FINOPS_ENABLED` (defaults off), fire-and-forget. What changes is its
*framing*: it's now explicitly an optional bonus integration (for model-finops's cross-tool
ML routing/semantic-caching), not the only way to see cost data. For air-gapped/government
deployments: leave `SILKROUTE_FINOPS_ENABLED=false` (already the default) and get full local
cost visibility with zero external network calls via `/budget/models` + the new dashboard
section. This also downgrades the previously-blocked live-Supabase E2E test from "blocking"
to "optional integration test, whenever someone actually wants model-finops's extra
features."

## Next steps

Implementation (schema, repository, route, dashboard section, tests) is a separate future
step, to be scoped via a detailed implementation plan before coding begins.

## Verification (for the future implementation step)

- New table appears after `psql -f sql/init.sql` (or container restart via `start.sh`) with no
  errors and no impact to existing tables.
- `rollup_day()` unit test mirroring `test_budget_snapshots.py`'s existing coverage.
- `GET /budget/models` integration test confirming correct route ordering (added before
  `{project_id}`) and fail-open behavior, mirroring `budget.py`'s existing route tests.
- Dashboard: `npm run build` clean, manually verify the new Budget-page section renders real
  data after running the AV demo (`agent_ready_av_demo.py --mock-pearl`) a few times to
  populate `cost_logs`.
