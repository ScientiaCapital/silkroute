# SilkRoute Backlog

**Updated:** 2026-03-22 (Phase 10 complete)

## Priority: Medium

| # | Item | Source | Effort | Impact | Owner | ETA |
|---|------|--------|--------|--------|-------|-----|
| 6 | Process rlimit enforcement (memory cap) | Observer WARNING (Phase 0) | M | Low | --- | Docker phase |
| 17 | Dashboard ESLint configuration (`next lint` requires setup) | Observer INFO (Phase 6) | XS | Low | --- | Future |
| 19 | SupervisorSessionResponse construction repeated in 3 routes — extract helper | Observer INFO (Phase 6b) | XS | Low | --- | Future |
| 20 | Supervisor route ordering risk: future routes must maintain GET /sessions before GET /sessions/{id} | Observer INFO (Phase 6b) | XS | Low | --- | Future |
| 21 | `_extract_cost()` still has silent `except Exception: pass` (canonical pattern) | Observer INFO (Phase 7) | XS | Low | --- | Future |
| 22 | Pre-existing test failures: 6 deepagents + 1 langchain_openai collection error | Observer INFO (Phase 7) | S | Low | --- | Future |
| 23 | Dockerfile HEALTHCHECK uses shell-form CMD with `${PORT:-8787}` — monitor on Railway deploy | Observer WARNING (Phase 9) | XS | Low | --- | First Railway deploy |
| 24 | AutoResearch: `code.py` runs pytest up to 3x per experiment (eval + build_context) — cache results | Observer INFO (Phase 10) | S | Low | --- | Future |
| 25 | AutoResearch: add Prompt Lab target (`targets/prompt.py`) | Plan (Phase 10) | M | Medium | --- | Future |
| 26 | AutoResearch: add Routing Optimizer target (`targets/routing.py`) | Plan (Phase 10) | M | Medium | --- | Future |
| 27 | AutoResearch: add dashboard page with live experiment leaderboard | Plan (Phase 10) | M | Medium | --- | Future |

## Priority: Low (future phases)

| # | Item | Source | Effort | Impact | Owner | ETA |
|---|------|--------|--------|--------|-------|-----|
| 11 | Auto-sync TypeScript models from Python | Backlog carry-forward | L | Low | --- | Future |
| 12 | GitHub webhooks (HTTP listener) | Phase 7 Full | L | Medium | --- | Future |
| 13 | WebSocket for dashboard live updates | Phase 7 Full | L | Medium | --- | Future |
| 14 | Background daemonization (fork/detach) | Phase 7 Full | M | Medium | --- | Future |
| 15 | API rate limiting tiers | Plan scope exclusion (Phase 2) | M | Medium | --- | Future |
| 16 | Ralph autonomy boundary — no human approval gate | Observer R1 (Phase 4) | M | Low | --- | Future |

## Resolved (This Session — Phase 10)

| Item | Resolution |
|------|-----------|
| AutoResearch engine | RESOLVED — 10 new files, engine.py experiment loop, git branch isolation |
| Code Improver target | RESOLVED — pytest + coverage + ruff eval, composite scoring |
| CLI integration | RESOLVED — `silkroute research start/status/results` commands |
| DA Gate: `git add -A` scope issue | RESOLVED — `_git_commit()` now accepts explicit `files` param |

## Resolved (Phase 9)

| Item | Resolution |
|------|-----------|
| Lint BLOCKER: ANN001/ANN202 on test_api_runtime.py:90 | RESOLVED — Added `AsyncGenerator[str, None]` annotations to `mock_stream` |
| Test fixture duplication in test_lifespan.py | RESOLVED — Replaced `_make_settings()` with conftest `test_settings` fixture |
| Test fixture duplication in test_cli.py | RESOLVED — Replaced `_make_test_settings()` with conftest `test_settings` fixture |
| Railway deployment infrastructure | RESOLVED — Dockerfile, start.sh, railway.toml, .dockerignore, docker-compose.prod.yml |

## Resolved (Phase 8)

| Item | Resolution |
|------|-----------|
| Lifespan context manager untested (#8) | RESOLVED — 8 tests in test_lifespan.py covering Redis/Postgres connect+fail+cleanup |
| SSE stream error paths untested (#9) | RESOLVED — 3 tests for TimeoutError, generic Exception, no [DONE] on error |
| CLI commands 0% coverage (#10) | RESOLVED — 31 tests in test_cli.py covering skills, context7, projects, and simple commands |

## Resolved (Phase 7)

| Item | Resolution |
|------|-----------|
| Broad `except Exception` in retry loops (#5) | RESOLVED — four-clause pattern (CancelledError/transient/permanent/fallback) across 9 files |
| Budget snapshot daily rollups (#7) | RESOLVED — budget_snapshots.py repo + scheduler cron + GET /budget/snapshots endpoint |
| Cache SkillRegistry as app.state (#4) | RESOLVED — app.state.skill_registry singleton via Depends(get_skill_registry) |

## Resolved (Phase 6b)

| Item | Resolution |
|------|-----------|
| Wire ContextManager into SupervisorRuntime (#1) | RESOLVED — dual-write pattern in _run_session() + stream() + _execute_step() |
| Add skill_executions DB repository (#3) | RESOLVED — skill_executions.py with INSERT, LIST, STATS + fire-and-forget in SkillRegistry |
| Task history page in dashboard (#18) | RESOLVED — tasks/page.tsx with session cards, step progress bars, status badges |

## Resolved (Previous Sessions)

| Item | Resolution |
|------|-----------|
| Consolidate SSRF protection into shared util (#2) | RESOLVED — unified in `network/ssrf.py` (Phase 6) |
| SSRF dual implementation drift risk | RESOLVED — single source of truth (Phase 6) |
| Broad `except Exception` in RalphController.run_cycle() (W1) | Narrowed to specific types (Phase 5) |
| Silent checkpoint failure logging (W2) | log.warning with error string (Phase 5) |
| Naive keyword decomposer (W4) | LLMDecomposer with cache + fallback (Phase 5) |
| OrchestratorRuntime.stream() broad except | Narrowed to specific exceptions (Phase 4) |
| BudgetMiddleware non-atomic budget | try_reserve()/settle() with asyncio.Lock (Phase 4) |
| OrchestratorRuntime.stream() sequential stages | asyncio.gather for parallel (Phase 4) |
| allocate_budget() mutates in place | copy.deepcopy (Phase 4) |
| Tool audit log persistence | db/repositories/tool_audit.py (Phase 3) |
| LegacyRuntime.stream() batch-not-stream | asyncio.Queue producer-consumer (Phase 3) |
| app.py broad except Exception | Narrowed to specific types (Phase 3) |
| SSE stream no timeout | stream_timeout_seconds: 300 (Phase 3) |
| Document _sandbox_config threading model | Docstring in tools.py (Phase 3) |
| Duplicate test_settings fixture | Shared in conftest.py (Phase 3) |

---

_Effort: XS (<1hr), S (1-3hr), M (3-8hr), L (1-2d)_

## 2026-07-12 — End Day findings
- [x] Verify DIRECT_MODEL_NAMES native model IDs + litellm prefixes (deepseek/, dashscope/, zai/) against vendor docs once API keys exist (best-guesses shipped 2026-07-11) — Qwen/GLM names confirmed correct; DeepSeek's `deepseek-chat`/`deepseek-reasoner` are being retired 2026-07-24, migrated to `deepseek-v4-flash`/`deepseek-v4-pro`. Also fixed a real bug found along the way: the premium-tier `deepseek-r1-0528` was mapped to the same "reasoner" alias as the free tier, which now silently resolves to Flash-tier reasoning instead of Pro — repointed to `deepseek-v4-pro`.
- [x] Verify new local Ollama tags `ollama/deepseek-r1:14b` and `ollama/glm4.6:9b` against `ollama search`/https://ollama.com/library before pulling — `deepseek-r1:14b` confirmed real (DeepSeek-R1-Distill-Qwen-14B, 9GB). `glm4.6:9b` does not exist — GLM-4.6 is a ~355B-param MoE model with no 9B variant; removed `GLM_CURRENT_LOCAL` entirely rather than guess a replacement.
- [x] Added `min_ram_gb` field to `ModelSpec` + tagged all local Ollama models (2026-07-12): only `glm4:9b` and the newly-added `qwen2.5:7b` fit an 8GB M1; `qwen2.5:14b`/`qwen2.5:32b`/`qwen3:30b-a3b`/`deepseek-r1:14b` all need 16GB+ and are only usable on the 24GB M4 or bigger.
- [x] Renamed `GLM_47_9B_LOCAL` → `GLM_4_9B_LOCAL` (2026-07-12) — the variable name implied GLM-4.7, but `glm4:9b` on Ollama's official library is plain GLM-4 (2024). A real newer small GLM (GLM-Z1-9B-0414) exists but only via a community (non-official) Ollama tag `sllm/glm-z1-9b` at 8.6GB — decided against adding it, staying consistent with this registry's official-`library/`-tags-only sourcing.
