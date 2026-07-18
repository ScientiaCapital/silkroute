# silkroute

**Branch**: main | **Updated**: 2026-07-18

## Status
Model-agnostic AI agent orchestrator (Chinese-LLM-optimized) — and the **AI-first orchestration
backbone** for the agentic AV control plane. On `main` (`2243dc1`): production security gate, MCP
server + N-server bridge, self-contained AV/edge demo, fit-to-hardware routing + `raspberry-pi`,
western frontier models, live SSE room view, a self-healing room-health `ResearchTarget`, **and now a
CLOSED self-healing loop** — detect fault → pick fix from the playbook → call an MCP action tool →
re-read to verify, watchable live on `/demo`. **1115 tests passing**; `ruff check src/` at the
5-error baseline. Positioning: **embrace** Hermes/OpenClaw as front-ends; SilkRoute sits **above** OpenAV.

## Done (This Session — closed the self-healing loop)
1. [x] **Shared playbook engine** (`320ab70`) — extracted `autoresearch/playbook.py`
       (`load_playbook`/`decide_action`/`KNOWN_ACTIONS`) so the scoring target AND the runtime
       executor use ONE engine. Pure refactor; room-health tests unchanged.
2. [x] **Mutable mock room + 6 action tools** (`1788965`) — `demo/mock_epiphan_mcp.py` is now a
       mutable Room320B; action tools (start_recorder, restart_input, rotate_recordings,
       remount_storage, reboot_device, throttle_channels) mutate state so a re-read verifies the fix.
       Fault injection via `SILKROUTE_MOCK_ROOM_FAULT`. Healthy defaults byte-compatible with before.
3. [x] **Remediation executor** (`c96d2c9`) — `autoresearch/heal.py` (`heal_room`/`heal_with_mock`)
       reuses `connect_mcp_server` + `ToolRegistry.execute` + the shared playbook. `demo/
       self_healing_demo.py` heals 3/6 with the seed playbook (matches the 0.67 score), 6/6 with a
       complete one. Executor uses its OWN allowlist (read+action); production allowlist stays read-only.
4. [x] **Watchable in the browser** (`2243dc1`) — un-gated `GET /demo/heal?fault=<type>` SSE + an
       "Inject fault → Heal" panel in `LiveRoomView`. Verified in a real browser (Playwright): inject
       signal_loss → streamed detect→fix→verify → "✓ Healed autonomously".

## Next
1. [ ] **Cloud model for a clean autoresearch keep** — set `SILKROUTE_OPENROUTER_API_KEY`, run
       `silkroute research start -t room-health -m deepseek/deepseek-v3.2`, then re-run
       `python demo/self_healing_demo.py` (the evolved playbook should heal more rooms). Local 14B
       mangles YAML — too weak for a clean keep.
2. [ ] **Surface autonomy in the dashboard** — no UI shows the experiment `Ledger`
       (`.silkroute/autoresearch/results.tsv`; `Ledger.read/recent/best/count`) or `agent_memories`
       (endpoint `/memories` exists, no page). A "Research/Autonomy" page is greenfield + high-signal.
3. [ ] **Wire western models into the dashboard Models page** — it's static (`dashboard/src/lib/
       models.ts`, 13 Chinese models, hardcoded "Chinese LLMs" copy); the API already serves all 21
       via `GET /models`. Either add 4 entries or switch the page to fetch live.
4. [ ] **Live `run_agent` mode for `/demo/stream`**; EC20 hardware verification (bench).

## Blockers
- No cloud provider key in `.env` → autoresearch clean-keep still blocked (local 14B flakes).
- Live AV run needs Pearl/EC20 + OpenAV orchestrator on the bench (EC20 endpoints are placeholders).

## Working from the AV side?
The AV control plane lives in the sibling repo **`epiphan-openav-bridge`** — start at its
**`HANDOFF.md`** (verified no-hardware smoke test + go-live steps). Canonical business strategy:
`../epiphan-pi-strategic-report.md`. Full plan: `~/.claude/plans/where-we-at-with-fluffy-popcorn.md`.

## Tech Stack
Python 3.12 (Click · Pydantic · FastAPI · litellm · asyncpg · redis · mcp · httpx) | Next.js 15
(React 19, Tailwind v4) | PostgreSQL 16 | Redis 7 | Ollama (local) | Docker Compose
