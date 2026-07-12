# silkroute

**Branch**: main | **Updated**: 2026-07-12

## Status
Ran a full `/begin` cycle today: context sync, both observer audits (0 BLOCKERs), standup, and an approved 5-item sprint closing out yesterday's "Tomorrow" list. Model registry is now hardware-aware (`min_ram_gb` on every local Ollama model, split across the user's 8GB M1 and this 24GB M4 Epiphan laptop) and DeepSeek's native model names were migrated ahead of the 2026-07-24 `deepseek-chat`/`deepseek-reasoner` retirement — caught a real bug where the premium reasoning tier had silently collapsed onto Flash-tier reasoning via that alias. Ollama was installed on this machine and the AV demo (`agent_ready_av_demo.py --mock-pearl`) ran live end-to-end successfully. 928/928 tests passing, lint clean. Two commits from this work (`ec27f29`, `57f69a2`) are already pushed to `origin/main`.

## Done (This Session)
- [x] Verified `deepseek-r1:14b` is a real Ollama tag; removed `GLM_CURRENT_LOCAL` (`glm4.6:9b`) — no such tag exists, GLM-4.6 is a ~355B MoE model with no 9B variant
- [x] Fixed `DIRECT_MODEL_NAMES`: migrated DeepSeek to `deepseek-v4-flash`/`deepseek-v4-pro` ahead of the legacy-name retirement; fixed `deepseek-r1-0528` silently downgrading to Flash-tier reasoning via the shared "reasoner" alias
- [x] Renamed `GLM_47_9B_LOCAL` → `GLM_4_9B_LOCAL` — `glm4:9b` is plain GLM-4 (2024), not GLM-4.7 as the old name implied; confirmed no real small current-gen GLM tag exists on the official Ollama library (uncommitted as of this write — small diff on top of the pushed commits)
- [x] Added `ModelSpec.min_ram_gb` + tagged every local model after the user flagged their 8GB M1 + this 24GB M4 as the two real target machines; added a genuinely 8GB-safe `qwen2.5:7b` entry
- [x] `loop.py`: added debug logging to `_extract_cost()`'s two previously-silent exception fallbacks
- [x] Installed Ollama via Homebrew (wasn't present on this machine), pulled `qwen2.5:14b`, ran the AV demo live — completed in 7 iterations, correctly reported room 320-B's recording status
- [x] `.env.example` + `docker-compose.prod.yml`: added `SILKROUTE_FINOPS_*` passthrough; `docs/av-demo-guide.md` finished with Telemetry-setup + Dry-run sections

## Blockers
None. (Previously: Task 5's live model-finops + Supabase telemetry test was blocked on the user creating a Supabase project. Reframed below — no longer gating anything.)

## Tomorrow
Implement the local cost/model dashboard per `docs/plans/2026-07-12-local-cost-dashboard-design.md`: a `model_cost_snapshots` table + repository (mirrors `budget_snapshots.py`), a new `GET /budget/models` route (mind the route-ordering gotcha — must be declared before `/budget/{project_id}`), and a "Cost by Model" section on the dashboard's Budget page. This reuses data silkroute's own Postgres already captures for every run (including local Ollama) — no new service, no Supabase needed. The earlier Supabase E2E test is now optional/non-blocking: model-finops is reframed as a bonus integration, not the way to get cost visibility — air-gapped/government deployments just leave `SILKROUTE_FINOPS_ENABLED=false` (already the default) and get full local visibility anyway.

## Tech Stack
Python 3.12 (Click + Pydantic + FastAPI + uvicorn + litellm + asyncpg + structlog + Rich + redis + apscheduler + mcp + httpx) | Next.js 15 (React 19, Tailwind v4) | PostgreSQL 16 | Redis 7 | LiteLLM | Docker Compose

## Session Stats
- Tests: 928 passing, lint clean (5 pre-existing ruff errors in cli.py/autoresearch, untouched)
- Commits today: 2 (`ec27f29` model/DeepSeek fixes, `57f69a2` telemetry docs/config closeout), both pushed
- Sprint: 4/5 tasks complete; #5 blocked on user-provided Supabase credentials

## Links
- GitHub: https://github.com/ScientiaCapital/silkroute
- epiphan-mcp-server: https://github.com/ScientiaCapital/epiphan-mcp-server
- model-finops: https://github.com/ScientiaCapital/model-finops

---

_Updated by `/begin` sprint-execution session. 2026-07-12._
