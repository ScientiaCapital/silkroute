# silkroute

**Branch**: main | **Updated**: 2026-07-12

## Status
Full day: model registry fixes (DeepSeek v4 migration, GLM naming, hardware-aware `min_ram_gb`)
pushed to `main` this morning, then a full brainstorm → design → implementation cycle for a
**fully local, zero-cloud-dependency cost/model dashboard** — motivated by a real requirement
that government/courts/military and privacy-conscious deployments can't tolerate phoning home
to cloud SaaS (like `model-finops`'s Supabase dependency). Built via subagent-driven
development in an isolated worktree/branch (`feature/local-cost-dashboard`): 6 tasks, each
implemented, spec-reviewed, and code-quality-reviewed independently. Two real bugs caught and
fixed via that review process before merge-readiness. Verified fully end-to-end against a real
Postgres container, a live AV demo run, a direct API call, and an actual browser render.
945/945 tests passing on the branch, `npm run build` clean. Branch pushed to `origin`, **not
yet merged into `main`** — merge decision deferred (Backlog #30).

## Done (This Session)
- [x] Model registry: DeepSeek native-name migration (`deepseek-v4-flash`/`-pro`, ahead of the
      2026-07-24 legacy retirement), GLM naming fix (`GLM_4_9B_LOCAL`), `min_ram_gb` hardware
      tagging, Ollama installed + AV demo verified live — all pushed to `main`
- [x] Local cost dashboard design brainstormed + validated with user, doc committed to `main`
- [x] Implementation plan written, DA-reviewed (caught a real gap: E2E verification could
      silently pass against an empty `cost_logs` table if Postgres wasn't actually reachable —
      fixed before execution)
- [x] All 6 implementation tasks complete on `feature/local-cost-dashboard`: schema
      (`model_cost_snapshots`), repository, `GET /budget/models` API route, scheduler wiring,
      dashboard "Cost by Model" section, full E2E verification
- [x] Two real bugs caught by code review and fixed pre-merge: a redundant DB index, and a
      dashboard aggregation bug that collapsed two different providers serving the same
      model into one row with a misleading provider label
- [x] End-of-day: observer findings dispositioned (2 resolved, 2 logged to Backlog #28/#29),
      security sweep clean (gitleaks + manual grep + `.env`/`.pem`/`.key` history, no leaks),
      portfolio metrics captured, `main` + `feature/local-cost-dashboard` both pushed

## Blockers
None.

## Tomorrow
Decide how to integrate `feature/local-cost-dashboard` into `main` — merge, PR, or otherwise —
via `superpowers:finishing-a-development-branch` (not done automatically). PR link already
available: https://github.com/ScientiaCapital/silkroute/pull/new/feature/local-cost-dashboard.
Separately, the live `model-finops` + Supabase telemetry test remains optional/non-blocking —
`model-finops` is now explicitly a bonus integration, not required for cost visibility, since
this branch delivers full local cost/model tracking with zero cloud dependency.

## Tech Stack
Python 3.12 (Click + Pydantic + FastAPI + uvicorn + litellm + asyncpg + structlog + Rich + redis + apscheduler + mcp + httpx) | Next.js 15 (React 19, Tailwind v4) | PostgreSQL 16 | Redis 7 | LiteLLM | Docker Compose

## Session Stats
- Tests: 928 passing on `main` / 945 passing on `feature/local-cost-dashboard`, lint clean
  (5 pre-existing ruff errors in cli.py/autoresearch, untouched, unrelated)
- Commits today: 5 on `main` (model registry + state sync), 7 on the feature branch
- Lines: +1,450/-19 on the feature branch (schema, repository, API, scheduler, dashboard, tests)
- Security: gitleaks clean, no `.env`/`.pem`/`.key` ever committed

## Links
- GitHub: https://github.com/ScientiaCapital/silkroute
- epiphan-mcp-server: https://github.com/ScientiaCapital/epiphan-mcp-server
- model-finops: https://github.com/ScientiaCapital/model-finops
- Design doc: `docs/plans/2026-07-12-local-cost-dashboard-design.md`
- Implementation plan: `docs/plans/2026-07-12-local-cost-dashboard-implementation.md` (on the feature branch)
- Open PR: https://github.com/ScientiaCapital/silkroute/pull/new/feature/local-cost-dashboard

---

_Updated by `/end` day-close workflow. 2026-07-12._
