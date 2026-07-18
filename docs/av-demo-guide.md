# Agent-Ready AV Demo Guide

A self-hosted, open-weight LLM (served locally via Ollama) answers a plain-English AV question
by calling [epiphan-mcp-server](https://github.com/ScientiaCapital/epiphan-mcp-server)'s tools
directly over MCP — no cloud dependency anywhere in the loop. This guide covers running it with
different local models and what shows up on the model-finops dashboard once telemetry is wired.

## Quickstart (fully self-contained — no external repo)

```bash
ollama pull qwen2.5:14b
python demo/agent_ready_av_demo.py --mock-mcp
```

`--mock-mcp` points the MCP bridge at the vendored `demo/mock_epiphan_mcp.py` — a tiny MCP server
that serves the 7 read tools (plus 6 remediation action tools used by the self-healing loop) from a
mutable Pearl-2-Room320B model. Nothing but silkroute + Ollama is
required: no `epiphan-mcp-server` clone, no Pearl hardware, no HTTP layer. This is the recommended
first-touch demo and mirrors what the dashboard's landing page (**Agent-Ready AV**, `/`) visualizes.

The dashboard's trace defaults to a scripted replay of this exact flow (zero external deps — works
even without Ollama running), but the **"Run live agent"** button on that page — or
`curl -N 'localhost:8787/demo/stream?live=true'` directly — runs this same script's logic for real,
live, over SSE.

Use `--mock-pearl` (below) or the live path only when you specifically want the *real*
`epiphan-mcp-server` in the loop.

## Prerequisites (for `--mock-pearl` / live hardware only)

- [Ollama](https://ollama.com) installed and `ollama serve` running.
- `epiphan-mcp-server` cloned as a sibling directory to `silkroute` (both under the same parent
  folder), with its own venv set up (`python -m venv .venv && pip install -e ".[dev]"`) — the
  demo script defaults to `../epiphan-mcp-server/.venv/bin/python` (override with
  `--epiphan-python` if your layout differs). Not needed for `--mock-mcp`.
- Real Pearl fleet credentials (`PEARL_DEVICES`/`PEARL_USERNAME`/`PEARL_PASSWORD`) if you want to
  run against live hardware instead of `--mock-pearl`.
- (Optional, for telemetry) model-finops running locally or reachable at some URL, with
  `FINOPS_INGEST_TOKEN` set on its side and `SILKROUTE_FINOPS_*` set on silkroute's side.

## Models to pull

| Model | Ollama tag | Status |
|---|---|---|
| Qwen2.5 14B | `qwen2.5:14b` | **Verified** — the demo's default |
| Qwen2.5 32B | `qwen2.5:32b` | **Verified** — larger, slower, same behavior |
| Qwen3 30B | `qwen3:30b-a3b` | **Verified** — pre-existing silkroute entry |
| GLM-4 9B | `glm4:9b` | **Verified**, but an older generation tag |
| DeepSeek R1 14B | `deepseek-r1:14b` | **Verified** (2026-07-12) — 9.0 GB, 128K context on ollama.com/library |
| ~~GLM-4.6 9B~~ | ~~`glm4.6:9b`~~ | ❌ **Invalid — no such tag.** Ollama publishes no `glm4.6`; current-gen GLM names are `glm-4.7` / `glm-5`. Use `glm4:9b` above, or pick a current tag from ollama.com/library and confirm its size with `ollama show <tag>` before pulling. |

Model tags drift — confirm any tag against [ollama.com/library](https://ollama.com/library) (or
`ollama show <tag>`) before pulling rather than trusting a registry entry. The silkroute registry
(`src/silkroute/providers/models.py`) is already corrected: the invalid `glm4.6:9b` guess was
removed (GLM-4.6 is a ~355B MoE model — no lightweight local tag exists), leaving `glm4:9b` as the
only local GLM option.

## Running the demo per model

```bash
ollama pull qwen2.5:14b   # or any tag from the table above

python demo/agent_ready_av_demo.py --mock-pearl \
    --model ollama/qwen2.5:14b
```

Swap `--model` for any registered `ollama/<tag>` to try a different one. Drop `--mock-pearl` and
pass `--pearl-devices`/`--pearl-username`/`--pearl-password` to run against a real fleet instead.

## Telemetry setup

Telemetry is opt-in and fire-and-forget — the agent never blocks or fails on a slow or unreachable
finops endpoint. To turn it on, set a matching shared secret on both sides.

On **silkroute** (host env, or your `.env` — the vars are documented in `.env.example`):

```bash
export SILKROUTE_FINOPS_ENABLED=true
export SILKROUTE_FINOPS_BASE_URL=http://localhost:8000   # where model-finops is reachable
export SILKROUTE_FINOPS_TOKEN=<shared-secret>            # any strong random string
```

On **model-finops** (its own env / `.env`):

```bash
export FINOPS_INGEST_TOKEN=<same-shared-secret>          # MUST equal SILKROUTE_FINOPS_TOKEN
```

The two tokens must be identical — the ingest endpoint (`POST /api/telemetry/ingest`) rejects a
mismatch or a missing token with HTTP 401. Confirm model-finops is actually up before demoing:

```bash
curl -fsS http://localhost:8000/health && echo "  finops up"
```

> **One-time DB step (model-finops side).** The ingest endpoint writes extra columns
> (`project_id`, `session_id`, `task_type`, `latency_ms`, `source`) that aren't in the base schema.
> Run `migrations/supabase_add_finops_ingest_columns.sql` once in the Supabase SQL Editor before the
> first real run, or those inserts fail. It's additive and idempotent — safe to re-run.

## What shows up on the model-finops dashboard

If `SILKROUTE_FINOPS_ENABLED=true` (plus `_BASE_URL`/`_TOKEN`) is set, each iteration reports to
model-finops's `/api/telemetry/ingest` endpoint. On the dashboard (`/dashboard`, or
`modelfinops.com/dashboard` if pointed at the hosted instance):

- **Shows up automatically**: request count and token totals in the by-provider chart, total
  spend, avg cost per request — these read straight from the same `requests` table/`GET /stats`
  every other request already uses.
- **Cost will read $0.00 for every row** — this is correct, not a bug. Local Ollama models have
  zero marginal cost by definition. Don't be alarmed seeing $0.00 next to a working demo.
- **Stored but not yet visible in the UI**: `project_id`, `session_id`, `task_type`, `latency_ms`
  — these land in the Supabase `requests` table (via the additive migration in
  `migrations/`) but no dashboard page renders them yet. Check via the Supabase table browser if
  you need them.

## Dry run — end to end

Run this once yourself before showing anyone. Anything in `<…>` is a placeholder for *your* live
output — fill it in from your own run rather than trusting these as fixed numbers.

```bash
# 1. Start the local model server (leave running in its own terminal)
ollama serve

# 2. Pull the model you'll demo (first time only — multi-GB download)
ollama pull qwen2.5:14b
ollama list                       # confirm the tag is present

# 3. (Optional) turn on telemetry — see "Telemetry setup" above
export SILKROUTE_FINOPS_ENABLED=true \
       SILKROUTE_FINOPS_BASE_URL=http://localhost:8000 \
       SILKROUTE_FINOPS_TOKEN=<secret>

# 4. Run the demo against a mock Pearl (no hardware needed)
python demo/agent_ready_av_demo.py --mock-pearl --model ollama/qwen2.5:14b
```

What a good run looks like:

- The agent calls epiphan-mcp-server's tools over MCP and returns a coherent plain-English answer:
  `<paste the final answer here — e.g. "Recording is active in room 320-B, started 14 min ago">`
- End-to-end latency for the local 14B model: `<~N s — record your own>`
- If telemetry is on, a fresh row appears on the model-finops dashboard within a few seconds, at
  **cost $0.00** (correct — local models have zero marginal cost; see the dashboard section above).

If you get an error instead of an answer, the usual causes are: `ollama serve` not running, the tag
not pulled (check `ollama list`), or `../epiphan-mcp-server/.venv` missing — pass `--epiphan-python`
to point at the right interpreter (see Prerequisites).

## Pre-demo checklist

1. `ollama serve` is running, and the model you intend to demo is actually pulled (`ollama list`).
2. If demoing telemetry: model-finops is reachable, `FINOPS_INGEST_TOKEN` matches on both sides,
   and you've hit its `/health` endpoint once to confirm it's actually up.
3. Run the demo once yourself, beforehand, end-to-end — confirm you get a coherent final answer
   and (if telemetry is on) that a fresh row shows up on the dashboard within a few seconds.
4. Know going in that the cost column will read $0.00 — mention it proactively rather than let it
   look like something's broken mid-demo.
