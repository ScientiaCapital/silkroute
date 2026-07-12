# Agent-Ready AV Demo Guide

A self-hosted, open-weight LLM (served locally via Ollama) answers a plain-English AV question
by calling [epiphan-mcp-server](https://github.com/ScientiaCapital/epiphan-mcp-server)'s tools
directly over MCP — no cloud dependency anywhere in the loop. This guide covers running it with
different local models and what shows up on the model-finops dashboard once telemetry is wired.

## Prerequisites

- [Ollama](https://ollama.com) installed and `ollama serve` running.
- `epiphan-mcp-server` cloned as a sibling directory to `silkroute` (both under the same parent
  folder), with its own venv set up (`python -m venv .venv && pip install -e ".[dev]"`) — the
  demo script defaults to `../epiphan-mcp-server/.venv/bin/python` (override with
  `--epiphan-python` if your layout differs).
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
| DeepSeek R1 14B | `deepseek-r1:14b` | ⚠️ **UNVERIFIED** — best-guess tag, run `ollama search deepseek` or check https://ollama.com/library before pulling |
| GLM-4.6 9B | `glm4.6:9b` | ⚠️ **UNVERIFIED** — best-guess at a current-gen GLM tag, same caveat |

For anything marked unverified, confirm the real tag first — don't assume it's correct just
because it's in the registry (`src/silkroute/providers/models.py` documents this same caveat
inline).

## Running the demo per model

```bash
ollama pull qwen2.5:14b   # or any tag from the table above

python demo/agent_ready_av_demo.py --mock-pearl \
    --model ollama/qwen2.5:14b
```

Swap `--model` for any registered `ollama/<tag>` to try a different one. Drop `--mock-pearl` and
pass `--pearl-devices`/`--pearl-username`/`--pearl-password` to run against a real fleet instead.

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

## Before sharing with Vadim — checklist

1. `ollama serve` is running, and the model you intend to demo is actually pulled (`ollama list`).
2. If demoing telemetry: model-finops is reachable, `FINOPS_INGEST_TOKEN` matches on both sides,
   and you've hit its `/health` endpoint once to confirm it's actually up.
3. Run the demo once yourself, beforehand, end-to-end — confirm you get a coherent final answer
   and (if telemetry is on) that a fresh row shows up on the dashboard within a few seconds.
4. Know going in that the cost column will read $0.00 — mention it proactively rather than let it
   look like something's broken mid-demo.
5. Per the earlier decision on this thread: don't frame this as an Epiphan partnership pitch —
   it's your own side-project work, shown as "here's what's possible," not an org-level ask.
