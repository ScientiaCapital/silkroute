# silkroute

**Branch**: main | **Updated**: 2026-07-17 (end of day)

## Status
Big day — four sprints landed on `main`, all merged `--no-ff` and pushed (origin/main @
`d2afdb9`). Repositioning SilkRoute to compete with persistent-agent frameworks (Hermes,
OpenClaw) drove the theme: **persistent memory + a genuinely autonomous, fully-local research
loop**. `1031/1031` tests passing on `main`; `ruff check src/` at the known 5-error baseline
(pre-existing cli.py/autoresearch E501s). Working tree clean, no stray local branches.

## Done (This Session)
- [x] **Persistent agent memory v1** (`57bbc40`) — Postgres `agent_memories` table, `remember`
      tool + top-K recall wired into `run_agent()` and (lightly) the supervisor; API
      (`GET/DELETE /memories`), CLI (`silkroute memory list/add/forget`), fail-open everywhere.
      Verified live vs real Postgres + Ollama incl. fail-open with DB down.
- [x] **Schema migration runner** (`7ee03d8`) — `schema_migrations` table + numbered
      `sql/migrations/*.sql` + `silkroute db status/migrate`. init.sql stays the fresh-install
      bootstrap; existing DBs catch up. Migration 0001 = agent_memories retroactively.
- [x] **AutoResearch → agent_memories bridge** (`ec2ad2e`) — keep/discard/crash outcomes logged
      to `agent_memories` (importance 0.6/0.3/0.2), `CodeImproverTarget.build_context()` recalls
      past learnings. Migration 0002 drops a project_id FK bug that had silently blocked any
      ad-hoc `--project` label from saving memories.
- [x] **Karpathy-faithful engine + local Ollama researcher** (`d2afdb9`) — see next section.

## AutoResearch finish-out (today's headline sprint, `d2afdb9`)
Grounded in Karpathy's real repo (github.com/karpathy/autoresearch — fetched README + program.md):
- Single-pytest-run **eval caching** (#24): 3 pytest runs/experiment → 1 (keep) or 2 (discard).
- **Wall-clock budgets**: `--hours` whole-run cap + `--experiment-timeout` (asyncio.wait_for)
  with pending-commit rollback; timeout → crash row + memory.
- **Keep-if-equal-but-simpler**: equal score + fewer lines → kept as `simplify:` (elegance rule).
- **Local Ollama researcher**: `propose_change()` branches to `litellm.acompletion` for
  `ollama/*` model ids — $0, zero-cloud, no API key. Plus 3 real bugs the live runs surfaced:
  shrink-context for local (70KB broke a 14B's JSON schema), **absolute-path validation bug that
  had blocked EVERY model**, complete-small-files (stop truncation-guessing), and a bounded
  re-prompt retry for local models.
- **Proven**: the full loop runs end-to-end fully locally (baseline → local 14B proposal →
  validate → apply → commit → re-eval → keep/discard/crash → ledger + agent_memories + rollback +
  circuit breaker), zero cloud dependency. **Not yet achieved**: a clean keep/discard — qwen2.5:14b's
  JSON-schema adherence is too stochastic even with 4 retries (probes succeed 3/3, full live prompts
  flake). This is a small-model limit, not a code limit.

## Tomorrow (team sprint setup)
1. [ ] **Get a real keep/discard on the record with a cloud Chinese model.** `--model
      deepseek/deepseek-v3.2` (the default) or GLM will clear validation reliably — cloud models
      get the full 20-file listing (the context reduction is local-only) and have solid JSON
      discipline. **BLOCKER: no cloud key configured** — no `.env`, all provider keys empty. Add
      `SILKROUTE_OPENROUTER_API_KEY` (one key covers DeepSeek/GLM/Qwen/Kimi) to `.env`, then run
      `silkroute research start --model deepseek/deepseek-v3.2 --max-experiments 3 --project autoresearch-live`.
      Today's absolute-path fix is what makes ANY cloud run viable (it would have crashed before).
2. [ ] **#27 leaderboard dashboard** — experiment leaderboard page over the ledger (Next.js page +
      API route), now that the loop actually produces interesting data. The visible/demo-able piece.
3. [ ] **#26 Routing Optimizer target** — second `ResearchTarget`, proves the protocol generalizes.
4. [ ] Optional: local runnability caveat — AutoResearch is fully local-capable but a 14B is too
      weak for clean keeps; document "use qwen2.5:32b+ or a cloud model for real runs."

## Blockers
- Cloud research runs need an API key in `.env` (see Tomorrow #1). Local runs work but flake on keeps.
- **GitHub cleanup decision pending**: stray remote branch `origin/claude/research-pi-dev-xTYJW`
  (single commit `f33edde`, 2026-02-27, "rebuild SilkRoute on pi.dev — TypeScript") — abandoned
  ~5-month-old TS-rewrite spike, NOT merged to main, superseded by the Python mainline. Left it
  in place (unmerged unique work, not mine to delete) — confirm before deleting from origin.

## Tech Stack
Python 3.12 (Click + Pydantic + FastAPI + uvicorn + litellm + asyncpg + structlog + Rich + redis + apscheduler + mcp + httpx) | Next.js 15 (React 19, Tailwind v4) | PostgreSQL 16 | Redis 7 | LiteLLM | Docker Compose | Ollama (local qwen2.5:14b/3b, qwen2.5vl:7b)

## Session Stats
- Tests: 1031/1031 passing on `main`; `ruff check src/` = 5 known pre-existing errors.
- Commits: 4 feature merges + supporting commits, all pushed to origin/main.
- 7 live local autoresearch runs (proving machinery; no clean keep — model-gated).
- Cost: non-gating per standing note — Epiphan covers.

## Competitive Framing (why the memory + autonomous-loop push)
Hermes Agent (Nous Research) and OpenClaw are single persistent local agents whose moat is
long-term memory + self-improvement + 24/7 autonomy. SilkRoute now has cross-session memory and a
Karpathy-style self-improvement loop; its differentiators remain cost governance + Chinese-LLM
routing + the MCP bridge. Remaining gaps vs those rivals: messaging reach (Telegram/Slack) and the
always-on daemon as the product's face.

## Links
- GitHub: https://github.com/ScientiaCapital/silkroute
- epiphan-mcp-server: https://github.com/ScientiaCapital/epiphan-mcp-server
- Karpathy autoresearch (design reference): https://github.com/karpathy/autoresearch

---

_Updated 2026-07-17 end of day (persistent memory + migrations + autoresearch memory bridge +
Karpathy-faithful engine & local Ollama researcher)._
