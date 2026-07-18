# silkroute

**Branch**: main | **Updated**: 2026-07-18

## Status
Model-agnostic AI agent orchestrator (Chinese-LLM-optimized) — and the **AI-first orchestration
backbone** for the agentic AV control plane. On `main` (`5713db6`): production security gate, MCP
server + N-server bridge, self-contained AV/edge demo (now with a **genuinely live agent mode**, not
just scripted replay), fit-to-hardware routing + `raspberry-pi`, western frontier models, a CLOSED
self-healing loop, and a **restructured dashboard** — the AV/Edge Demo is the landing page (`/`),
everything else (Overview/Projects/Models/Budget/Task History/Autonomy) lives under `/ops/*`.
**1124 tests passing**; `ruff check src/` clean (0 errors). Positioning: **embrace** Hermes/OpenClaw
as front-ends; SilkRoute sits **above** OpenAV.

## Done (This Session — sprint: harden, restructure, ship)
1. [x] **Tech-debt cleanup** (`560e332`, `9f5ba33`) — 5 ruff errors in `cli.py`, dead
       `ANN101/ANN102` ruff-ignore, deduped 3x-repeated `SupervisorSessionResponse` construction
       into `_session_to_response`/`_steps_to_response` helpers.
2. [x] **Dashboard tooling** (`061156a`) — real ESLint config (`next lint` had none, prompted
       interactively). `next`/`eslint-config-next` `^15.1.0`→`^15.5.20` (still the 15.x line — every
       flagged CVE's fix ceiling was ≤15.5.18, no Next 16 migration) + a scoped `postcss` override.
       `npm audit`: 2 vulnerabilities → 0.
3. [x] **Live Models page + Autonomy/Ledger page** (`afc8721`) — Models page now fetches
       `GET /models` live (21 entries incl. Claude Sonnet 5/GPT-5.6/Gemini 3.5), static list kept as
       offline fallback. New `GET /research/ledger` route (none existed) + `/ops/autonomy` page
       surfacing the experiment ledger + `agent_memories` — previously invisible except via raw
       TSV/DB access.
4. [x] **Live `run_agent` mode for `/demo/stream`** (`423a38b`) — `?live=true` spawns a real
       `run_agent()` loop over local Ollama against the mock MCP server (translates its coarser
       `stream_queue` vocabulary into the dashboard's `TraceEvent` shapes). Default replay unchanged.
       Real-hardware testing surfaced and fixed: a `project_id` FK-violation warning, an anyio
       cross-task-cancellation `RuntimeError` on timeout-cancel (broadened but not 100% eliminated —
       an orphaned `mcp`-internal sub-task can still log noise; documented as an accepted upstream
       limitation, not app-fixable without changing how `run_agent` connects to MCP servers), a
       silent-cutoff when the model loops without concluding (now an honest "reached the step limit"
       answer), a concurrency semaphore (2 concurrent streams, immediate "server busy" past that)
       since the endpoint is public/unauthenticated and now does real work, and a visible error
       banner in the dashboard when a live run ends in error/timeout (previously: silently went idle).
5. [x] **Dashboard IA restructuring** (`5713db6`) — validated against Epiphan's own public
       `agent-ready-av` page (no pricing disclosed anywhere, no vendor-lock-in framing): most of the
       dashboard read as an internal ops console, not the "exciting" front door. `/` now renders the
       AV/Edge Demo; Overview/Projects/Models/Budget/Task History/Autonomy moved to `/ops/*`; old
       paths redirect. Pure navigation move, no content redesign.
6. [x] **Fixed the real Vercel production deployment failure** — the `silkroute` Vercel project's
       **Root Directory setting was `.` (repo root) instead of `dashboard/`**, so every single
       production deployment for 147 days (since the project was created) built from the Python
       package root, found no Next.js app, and errored in ~2s. Removing the local root `.vercel/`
       duplicate link (an earlier, real but insufficient fix) only addressed local CLI/editor
       confusion — it did not touch this cloud-side setting. Fixed via `npm i -g vercel@latest`
       (50.4.11 → 56.3.1, to get the `vercel api` command) then
       `vercel api /v9/projects/prj_wwNbeQiXuLves4Zdv4MNcUtEAtxQ -X PATCH -F rootDirectory=dashboard`.
       Verified: redeployed the latest existing commit, got a real ~41s build instead of an instant
       error, `● Ready`, live site at `https://silkroute-sepia.vercel.app` returns 200 with the
       correct page title. Future git pushes to `main` should now deploy successfully too.
7. [x] **OpenRouter API key configured** — `SILKROUTE_OPENROUTER_API_KEY` set in local `.env`
       (gitignored; not pushed). Verified: key loads via `_resolve_api_key()`, OpenRouter
       `/api/v1/models` returns 200 (344 models). Unblocks cloud-model autoresearch keep.

## Next
1. [ ] **Cloud model for a clean autoresearch keep** — run
       `silkroute research start -t room-health -m deepseek/deepseek-v3.2`, then re-run
       `python demo/self_healing_demo.py`. Local 14B mangles YAML — too weak for a clean keep.
2. [ ] **EC20 hardware verification** (bench) — EC20 endpoints are still placeholders.
3. [ ] Consider whether the live-demo's residual "Task exception was never retrieved" log noise
       (upstream `mcp`/anyio interaction, see Done #4) is worth reporting upstream to the `mcp`
       Python SDK, or revisiting with a cooperative-cancellation approach in `run_agent` itself.

## Blockers
- Live AV run needs Pearl/EC20 + OpenAV orchestrator on the bench (EC20 endpoints are placeholders).

## Working from the AV side?
The AV control plane lives in the sibling repo **`epiphan-openav-bridge`** — start at its
**`HANDOFF.md`** (verified no-hardware plug-and-play).

## Tech Stack
Python 3.12 (Click · Pydantic · FastAPI · litellm · asyncpg · redis · mcp · httpx) | Next.js 15
(React 19, Tailwind v4) | PostgreSQL 16 | Redis 7 | Ollama (local) | Docker Compose
