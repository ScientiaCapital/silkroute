# silkroute

**Branch**: main | **Updated**: 2026-07-21

## Status
Model-agnostic AI agent orchestrator (Chinese-LLM-optimized) — and the **AI-first orchestration
backbone** for the agentic AV control plane. On `main` (`e848b3e`): production security gate, MCP
server + N-server bridge (epiphan + **openav presets**), self-contained AV/edge demo with live agent
mode, **hardware-aware fit-to-hardware routing (now actually wired)**, western frontier models incl.
**Claude Haiku 4.5**, a CLOSED self-healing loop, restructured dashboard. **Suite fully green:
1141 passed / 0 failed** (first time since the 9/9 playbook landed); `ruff check src/` clean.
Positioning: **embrace** Hermes/OpenClaw as front-ends; SilkRoute sits **above** OpenAV;
**epiphan-mcp-server (Vadim's) = the fleet plane we integrate with, never fork**.

## Done (This Session — "Vadim-Ready" sprint stories A–E, 2026-07-21)
1. [x] **Dual adversarial audit** (devil's-advocate observer + stakeholder pass; records in
       `.claude/observers/`) → all BLOCKERs/RISKs fixed: `run_agent` no longer constructs the full
       `SilkRouteSettings` (new narrow `DeploymentConfig` — the provider validator raised in keyless
       envs, breaking 20 tests in CI-like environments); router local-fit now **gated on
       `SILKROUTE_OLLAMA_ENABLED`** (a RAM-rich profile alone can no longer route to an Ollama that
       isn't running); openav allowlist corrected (added `ec20_jog`+`ec20_preset_save`, dropped
       uncalibrated `ec20_ptz`, catalog is 12 tools); "~115 tools" → ~130 (Vadim's actual count);
       generic IPs/creds in templates; bridge guide truth-ups.
2. [x] **Green main** — PR #2: frozen fixture seed (`tests/fixtures/seed_remediation_rules.yaml`,
       byte-exact pre-PR#1 playbook) for the 7 seed-narrative tests + live-playbook 9/9 invariant
       tests + finops env isolation (cross-test pollution via upstream `load_dotenv()`). 1132 passed.
3. [x] **Edge sprint merged** — PR #3: Claude Haiku 4.5 ModelSpec (STANDARD, latency-first western
       option, registry 21→22); hardware-profile wire into `run_agent()`→`select_model()` (was dead
       code); local-fit FREE+STANDARD (PREMIUM always cloud; Pi=0GB delegates all);
       `SILKROUTE_MCP_OPENAV_*` preset (read-only default, `MUTATING` opt-in via `--read-only`);
       `docs/edge-deployment.md` (RPi5/Ubuntu room controller); README EC20 truth-up.
4. [x] **Bridge repo** — parallel session shipped the full EC20 hybrid driver to bridge main
       (VISCA tcp/5678 + jog/preset_save tools + Pi runbook); our audit doc fixes merged as bridge
       PR #1 (Pearl-claims honesty, systemd `.env` gap, 12-tool count).
5. [x] **Mock stack-up PROVEN (sprint Story E)** — SilkRoute spawned openav-mcp (stdio, mock,
       read-only): `mcp_bridge_connected tools_discovered=3 tools_registered=3`; agent called
       `pearl_status(device='room-pearl')` + `ec20_status(device='room-cam')` and reported status.
       3 iterations, <$0.01 (deepseek-v3.2). Trace: scratchpad `story_e_full.log`.

## Next (sprint stories F–H — F is the send gate)
1. [ ] **F: LIVE hardware verify** — needs: Mac on the 192.168.8.x AV switch (NordVPN OFF — it
       auto-reconnects), Pearl admin password, safe recording window. Then: re-discover DHCP IPs →
       EC20 degree↔unit calibration sweep → set `panUnitsPerDegree`/`tiltUnitsPerDegree` in bridge
       `driver.go` (+ re-add `ec20_ptz` to the allowlist) → first live Pearl REST contact → e2e
       agent demo (`MUTATING=true`) with captured trace.
2. [ ] **G: Vadim package** — `docs/ECOSYSTEM.md` (3-repo roles/boundaries/seams,
       shipped-vs-vision, hardware-verified matrix) + email-ready brief + PROJECT_CONTEXT refreshes.
3. [ ] **H: send-readiness checklist** (see plan file / task board).
Backlog (papercuts from audits): fail-loud when an enabled MCP preset registers 0 tools; MCP stdio
env docstring overclaims (SDK forwards only a 6-var allowlist); live-event latency timing test on
real hardware; PROJECT_CONTEXT Pearl-IP history says 192.168.10.1 — operational value is 192.168.8.4.

## Done (2026-07-18 PM — live EC20 control + cloud autoresearch)
1. [x] **First real device control** — reached the live EC20 PTZ camera (`192.168.8.11`, DHCP) after
       finding **NordVPN NordLynx was blackholing the LAN**. Mapped its real control surface: Digest
       auth (not Basic), a proprietary JWT-gated `/api` dispatcher (OEM "VHDIPC", fw 3.3.40), and —
       the win — **VISCA-over-IP on tcp/5678**. Drove a real bounded pan→restore cycle; camera
       returned ACK + completion frames. The bridge's REST/Basic `driver.go` is wrong for the EC20.
       Full facts in memory `ec20-real-device-facts`.
2. [x] **Cloud autoresearch unblocked** — `SILKROUTE_OPENROUTER_API_KEY` + `deepseek/deepseek-v3.2`
       ran real bounded loops (a local 14B was too weak). Code target: baseline `0.964`, two legit
       proposals correctly DISCARDED (no headroom) + 1 no-op crash caught. **room-health: 6/9 → 9/9**
       fault remediation across 3 kept experiments, merged to `main` via **PR #1** (`a232360`).
3. [x] **EC20 VISCA build plan approved** for next session — rework only `driver.go` (REST→VISCA);
       MCP tool contract + Python layer + SilkRoute stay unchanged; AI tracking deferred. Plan
       captured in memory `ec20-real-device-facts`.

## Done (prior session — sprint: harden, restructure, ship)
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

## Resolved from earlier sessions (kept for history; see the 2026-07-21 sections above)
- EC20 VISCA driver build: SHIPPED (bridge main `70b2822`+; SilkRoute wiring in PR #3).
- Pearl Mini routing red herring: the `192.168.10.1` lead was the router's other leg — the Pearl is
  **`192.168.8.4`** on the same subnet as the EC20 (per the on-device screen); live contact pending
  (sprint Story F).
- Still open (backlog): the live-demo's "Task exception was never retrieved" log noise (upstream
  `mcp`/anyio interaction) — report upstream or cooperative cancellation in `run_agent`.

## Working from the AV side?
The AV control plane lives in the sibling repo **`epiphan-openav-bridge`** — start at its
**`HANDOFF.md`** (verified no-hardware plug-and-play).

## Tech Stack
Python 3.12 (Click · Pydantic · FastAPI · litellm · asyncpg · redis · mcp · httpx) | Next.js 15
(React 19, Tailwind v4) | PostgreSQL 16 | Redis 7 | Ollama (local) | Docker Compose
