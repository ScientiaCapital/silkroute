# silkroute

**Branch**: main | **Updated**: 2026-07-17

## Status
Model-agnostic AI agent orchestrator (Chinese-LLM-optimized) — and the **AI-first orchestration
backbone** for the agentic AV control plane. Phases 0–3 + the model-agnostic/live-room/self-healing
sprint are on `main` (`70b8055`): production security gate, MCP server (`silkroute mcp serve`) +
N-server client bridge, self-contained AV/edge demo, fit-to-hardware routing + `raspberry-pi` profile,
**western frontier models** in the registry, a **live SSE room view**, and a **self-healing
room-health ResearchTarget**. **1092 tests passing**; `ruff check src/` at the 5-error baseline.
Positioning: **embrace** Hermes/OpenClaw as front-ends (not compete); SilkRoute sits **above** OpenAV.

## Done (This Session — model-agnostic + live room + self-healing sprint)
1. [x] **Western frontier models** (`fa6097b`) — Claude Sonnet 5 + GPT-5.6 Sol (PREMIUM), Gemini 3.5
       Flash + GPT-5.6 Luna (STANDARD) as one-line `ModelSpec`s; provider=ANTHROPIC/OPENAI/GOOGLE route
       via the OpenRouter fallback with **zero router changes**. Registry 17→21. Chinese/local stay
       first in every routing chain (local-first posture). Slugs/pricing verified vs openrouter.ai.
2. [x] **Live SSE room view** (`e0d7697`) — new un-gated `/demo/room` + `/demo/stream` (SSE
       Think→Act→Observe trace, driven by the real mock tool output). Dashboard `/demo` now streams
       live via a `"use client"` `LiveRoomView` (EventSource) with static fallback. Verified end-to-end
       in a real browser (Playwright): LIVE badge + streamed trace + live fleet row.
3. [x] **Self-healing room-health target** (`70b8055`) — 2nd `ResearchTarget` (#26). Agent evolves a
       remediation **playbook** (`demo/room_health/remediation_rules.yaml`) scored against held-out
       fault scenarios; playbook-as-artifact fits the file-edit/git engine with **no engine changes**.
       Metrics mapped onto existing fields. Smoke-run verified end-to-end (14B correctly targeted the
       unhandled fault, engine discarded the mangled YAML — clean keep needs a cloud model, see below).

## Next
1. [ ] **Cloud model for a clean autoresearch keep** — set `SILKROUTE_OPENROUTER_API_KEY`, run
       `silkroute research start -t room-health -m deepseek/deepseek-v3.2` (local 14B mangles YAML;
       too weak for a clean keep — confirmed in the smoke run).
2. [ ] **Live `run_agent` mode for `/demo/stream`** — swap the deterministic replay for a real agent
       run when a model is reachable (query toggle); the replay stays the zero-dep default.
3. [ ] EC20 hardware verification; dashboard live-room view for real rooms (once Pearl/EC20 on bench).

## Blockers
- No cloud provider key in `.env` → autoresearch clean-keep still blocked (local 14B flakes; smoke-
  confirmed the engine discards its bad edits safely).
- Live AV run needs Pearl/EC20 + OpenAV orchestrator on the bench (EC20 endpoints are placeholders).

## Working from the AV side?
The AV control plane lives in the sibling repo **`epiphan-openav-bridge`** — start at its
**`HANDOFF.md`** (verified no-hardware smoke test + go-live steps). Canonical business strategy:
`../epiphan-pi-strategic-report.md`. Full plan: `~/.claude/plans/where-we-at-with-fluffy-popcorn.md`.

## Tech Stack
Python 3.12 (Click · Pydantic · FastAPI · litellm · asyncpg · redis · mcp · httpx) | Next.js 15
(React 19, Tailwind v4) | PostgreSQL 16 | Redis 7 | Ollama (local) | Docker Compose
