# silkroute

**Branch**: feature/local-cost-dashboard | **Updated**: 2026-07-12

## Status
Built and verified end-to-end a fully local, zero-cloud-dependency cost/model dashboard,
brainstormed and planned earlier today after the user raised a real requirement: for
government/courts/military and privacy-conscious deployments, phoning home to any cloud SaaS
(like model-finops's Supabase dependency) is disqualifying. Design doc committed to `main`
at `3b022ea`; this branch (`feature/local-cost-dashboard`, in `.worktrees/local-cost-dashboard`)
implements it via subagent-driven development — 6 tasks, each implemented, spec-reviewed, and
code-quality-reviewed independently before the next started. All 6 done. 945/945 tests
passing on this branch, `npm run build` clean, and the whole pipeline verified live against a
real Postgres container + the AV demo + a real browser session.

## Done (This Session)
- [x] Task 1: `model_cost_snapshots` table in `sql/init.sql` (mirrors `budget_snapshots`'
      BIGSERIAL-PK + UNIQUE convention) — one review round-trip fixed a redundant index
- [x] Task 2: `db/repositories/model_cost_snapshots.py` (`rollup_day`, `get_snapshots`),
      12 tests, mirrors `budget_snapshots.py` exactly but grouped by
      `project_id, model_id, provider`
- [x] Task 3: `GET /budget/models` route in `api/routes/budget.py`, declared before
      `/{project_id}` (route-ordering rule, confirmed correct by 2 independent reviews),
      4 tests including a shadow-route regression guard
- [x] Task 4: wired the new rollup into the daemon scheduler's existing daily
      `_budget_rollup()` cron tick alongside `budget_snapshots.rollup_day()` — no new schedule
- [x] Task 5: dashboard "Cost by Model" section on the Budget page — one review round-trip
      fixed a real bug (same `model_id` served by two different providers, e.g. direct
      DeepSeek vs. OpenRouter fallback, was collapsing into one misleading row; now keyed on
      `model_id::provider` to match the backend's actual grouping grain)
- [x] Task 6: end-to-end manual verification — started a real Postgres container, confirmed
      connectivity before trusting any row counts (a devil's-advocate review had flagged that
      `persist_sessions` defaulting to `True` doesn't guarantee Postgres is actually reachable),
      ran the AV demo live to generate real `cost_logs` rows, triggered the rollup manually
      against real Postgres, hit `GET /budget/models` directly (real JSON response), and
      visually confirmed the dashboard renders it via a real browser session
      (`ollama/qwen2.5:14b`, 18 requests, 37,199 tokens, $0.0000 — all correct)

## Blockers
None.

## Tomorrow
Decide how to integrate `feature/local-cost-dashboard` back into `main` (merge, PR, or
otherwise) via `superpowers:finishing-a-development-branch` — not done automatically as part
of this work. Separately: the earlier live model-finops + Supabase telemetry test remains
optional/non-blocking — model-finops is now explicitly a bonus integration, not required for
cost visibility, since this branch delivers full local cost/model tracking with zero cloud
dependency.

## Tech Stack
Python 3.12 (Click + Pydantic + FastAPI + uvicorn + litellm + asyncpg + structlog + Rich + redis + apscheduler + mcp + httpx) | Next.js 15 (React 19, Tailwind v4) | PostgreSQL 16 | Redis 7 | LiteLLM | Docker Compose

## Session Stats
- Tests: 945 passing on this branch (up from 928 on `main`, +17 new tests across Tasks 2-3-4),
  `npm run build` clean
- Commits on `feature/local-cost-dashboard`: dec8eb8 → 395b490 → 77e1d14 → 52e07b3 → 35185af
  → 42ef35d → da19610 (7 commits, including 2 review-driven fix commits)
- All 6 plan tasks complete, each independently spec-reviewed and code-quality-reviewed

## Links
- GitHub: https://github.com/ScientiaCapital/silkroute
- epiphan-mcp-server: https://github.com/ScientiaCapital/epiphan-mcp-server
- model-finops: https://github.com/ScientiaCapital/model-finops
- Design doc: `docs/plans/2026-07-12-local-cost-dashboard-design.md`
- Implementation plan: `docs/plans/2026-07-12-local-cost-dashboard-implementation.md`

---

_Updated by subagent-driven-development execution session. 2026-07-12._
