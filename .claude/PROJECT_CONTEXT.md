# silkroute

**Branch**: main | **Updated**: 2026-07-17

## Status
Model-agnostic AI agent orchestrator (Chinese-LLM-optimized) — and the **AI-first orchestration
backbone** for the agentic AV control plane. Phases 0–3 are merged to `main` and pushed (`4adee68`):
production security gate, MCP server (`silkroute mcp serve`) + N-server client bridge, self-contained
AV/edge demo (`--mock-mcp`, dashboard `/demo`), and fit-to-hardware routing + `raspberry-pi` profile.
**1078 tests passing**; `ruff check src/` at the 5-error baseline. Docs are handoff-ready.
Positioning: **embrace** Hermes/OpenClaw as front-ends (not compete); SilkRoute sits **above** OpenAV.

## Today's Focus (next session)
1. [ ] **Wire western frontier models** — add Claude/GPT/Gemini `ModelSpec` entries (one OpenRouter
       line each; no router changes) to make "fully model-agnostic" real in the registry.
2. [ ] **Self-healing hook** — a room-health `ResearchTarget`/Ralph task (detect fault → fix → verify)
       — the autonomy moat. (Second `ResearchTarget` also proves the protocol generalizes, #26.)
3. [ ] **Dashboard live-room view** — extend `/demo` into a live room/agent-trace view (the screen for
       leadership).
4. [ ] **Cloud model for a clean autoresearch keep** — set `SILKROUTE_OPENROUTER_API_KEY`, run
       `silkroute research start --model deepseek/deepseek-v3.2` (14B local is too weak for clean keeps).

## Done (This Session)
- Phases 0–3 (security gate, MCP server + N-server bridge, self-contained AV demo, fit-to-hardware
  routing) — merged to `main`, pushed, 1078 tests green.
- Built `openav-mcp` (in sibling `epiphan-openav-bridge`) + proved SilkRoute→openav-mcp round-trip.
- Strategy pass (JTBD/Blue Ocean/BMC) reconciled with `../epiphan-pi-strategic-report.md`; corrected
  positioning (SilkRoute above OpenAV; brands separate); model-agnostic pivot.
- Handoff-ready docs across silkroute + the bridge.

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
