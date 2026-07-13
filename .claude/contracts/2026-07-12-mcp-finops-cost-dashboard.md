# Feature Contract: MCP Bridge + model-finops Telemetry + Local Cost Dashboard

**Date:** 2026-07-12 (retroactive — work shipped across the 2026-07-12 sessions; contract
added per Backlog #28 to close the missing scope-of-work record)

## Inputs
- Per-iteration usage data from the agent loop (`src/silkroute/agent/loop.py`):
  provider, model, tokens, cost, latency, session/project IDs
- `cost_logs` rows in silkroute's self-hosted Postgres (already captured for every run,
  including free/local Ollama)
- Env config: `SILKROUTE_FINOPS_*` (enabled flag, base URL, shared bearer token)

## Outputs
- **MCP bridge** (`src/silkroute/mcp_bridge/client.py`): client for external MCP servers
  (e.g. epiphan-mcp-server) usable as agent tools
- **finops telemetry** (`src/silkroute/integrations/finops_client.py`): fire-and-forget
  POST to model-finops `POST /api/telemetry/ingest` — optional bonus integration
- **Local cost dashboard**: `model_cost_snapshots` table + repository, daily rollup,
  `GET /budget/models` API, "Cost by Model" section on the dashboard Budget page

## Invariants
- **Zero cloud dependency for cost visibility** — the local dashboard path must work with
  only self-hosted infra (Postgres container OK, cloud SaaS disqualifying). model-finops/
  Supabase is strictly optional, never required.
- Telemetry reporting is fail-open and fire-and-forget: any network/API error is logged
  and swallowed; a finops outage must never stall or break the agent loop.
- Rollup is idempotent (UPSERT on `project_id, model_id, provider, snapshot_date`) and
  rides the existing scheduler tick (00:05 UTC, same tick as `budget_snapshots`) — no
  second schedule.
- `GET /budget/models` is fail-open like the rest of `budget.py`: Postgres unreachable →
  empty list, never a 500.
- Route ordering: `/budget/models` declared **before** `/budget/{project_id}` (FastAPI
  parameterized-route shadowing — bit this project before).
- Dashboard aggregation grain is `model_id::provider` (two providers serving the same
  model must not collapse into one row).
- All existing tests keep passing (945 as of merge, `a581b0c`).

## Scope Boundary
- **In scope:** MCP bridge client, FinopsConfig + reporting hook in the agent loop,
  `model_cost_snapshots` schema/repository/rollup, `GET /budget/models`, dashboard
  Cost-by-Model section, E2E verification against real Postgres
- **Out of scope:** multi-user/LAN deployments (v1 is single local operator), standalone
  viewer app, `avg_latency_ms` column (deferred — data already in `cost_logs`), live
  model-finops + Supabase test (optional/non-blocking), date-range index on
  `model_cost_snapshots` (revisit if query patterns need it)

## API Surface
| Method | Path | Auth | Purpose |
|--------|------|------|---------|
| GET | /budget/models?project_id=&start_date=&end_date= | Yes | Per-model/provider daily cost snapshots |

## Architecture
`cost_logs` (written by the agent loop, all providers incl. local Ollama) → nightly
`rollup_day()` in `db/repositories/model_cost_snapshots.py` (mirrors
`budget_snapshots.py`) → `GET /budget/models` → dashboard Budget page. finops telemetry
is a parallel, optional fire-and-forget branch off the same loop hook. Design/impl docs:
`docs/plans/2026-07-12-local-cost-dashboard-{design,implementation}.md`.
