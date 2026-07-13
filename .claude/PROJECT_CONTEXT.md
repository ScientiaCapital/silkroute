# silkroute

**Branch**: main | **Updated**: 2026-07-12 (evening session)

## Status
Evening session: landed the local cost dashboard. `feature/local-cost-dashboard` merged into
`main` via direct `--no-ff` merge (`a581b0c`) — code merged 100% clean (only `.claude/` state
files conflicted, resolved by keeping main's newer end-day versions). Post-merge verification
on `main`: **945/945 tests passing** (the 6 known deepagents failures did not reproduce this
run), `ruff` clean except the 5 known pre-existing errors (cli.py/autoresearch), dashboard
`npm run build` clean. Pushed; worktree `.worktrees/local-cost-dashboard` removed, feature
branch deleted locally and on origin. Backlog #28/#29/#30 all resolved. The local
zero-cloud-dependency cost/model tracking story is now fully on `main`.

## Done (This Session)
- [x] #30: Merged `feature/local-cost-dashboard` → `main` (`a581b0c`), verified (945/945,
      build clean), pushed, worktree + branch cleaned up (local and origin)
- [x] #29: CLAUDE.md architecture diagram — added `demo/`, `docs/`, `scripts/`; fixed stale
      dashboard page count (3 → 5 pages) (`9007496`)
- [x] #28: Retroactive scope-of-work contract written:
      `.claude/contracts/2026-07-12-mcp-finops-cost-dashboard.md` (MCP bridge + finops
      telemetry + local cost dashboard: inputs/outputs/invariants/scope boundary)
- [x] Backlog.md updated — #28/#29/#30 moved to Resolved; code-review optional follow-ups
      captured as new #31 (date-range index + rollup SQL test coverage, non-blocking)

## Blockers
None.

## Tomorrow
Tomorrow: AutoResearch #27 experiment leaderboard dashboard page (recommended, not yet
confirmed) via feature-dev + dashboard page pattern (`tasks/page.tsx` + repository + API
route) | single builder, no worktree needed | Est: half day, ~$10-20 | Observer notes: no
unresolved flags; `.env` missing at repo root — copy from `.env.example` before any
live-service run. Alternatives: #26 Routing Optimizer target, #25 Prompt Lab, or hygiene
sweep (#17/#19/#21/#31). **Railway is off the table for now per Tim (2026-07-12)** — don't
propose the first deploy.

## Tech Stack
Python 3.12 (Click + Pydantic + FastAPI + uvicorn + litellm + asyncpg + structlog + Rich + redis + apscheduler + mcp + httpx) | Next.js 15 (React 19, Tailwind v4) | PostgreSQL 16 | Redis 7 | LiteLLM | Docker Compose

## Session Stats
- Tests: 945/945 passing on merged `main`, lint clean (5 known pre-existing ruff errors)
- Commits: merge commit + docs fix + state sync
- Cost: MTD $597.29 (non-gating per standing note — Epiphan covers)

## Links
- GitHub: https://github.com/ScientiaCapital/silkroute
- epiphan-mcp-server: https://github.com/ScientiaCapital/epiphan-mcp-server
- model-finops: https://github.com/ScientiaCapital/model-finops
- Design doc: `docs/plans/2026-07-12-local-cost-dashboard-design.md`
- Implementation plan: `docs/plans/2026-07-12-local-cost-dashboard-implementation.md`
- Contract: `.claude/contracts/2026-07-12-mcp-finops-cost-dashboard.md`

---

_Updated 2026-07-12 evening session (merge + backlog cleanup)._
