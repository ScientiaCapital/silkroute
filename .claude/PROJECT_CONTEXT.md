# silkroute

**Branch**: main | **Updated**: 2026-02-28

## Status
Phase 1 (OpenRouter + Deep Agents Foundation) complete on `main`. DeepAgentsRuntime stub replaced with working implementation backed by deepagents v0.4.4. OpenRouter adapter via ChatOpenAI base_url override. Code Writer as first functional Deep Agent. MantisConfig added to settings. 288/288 tests passing. Lint clean.

## Done (This Session — Phase 1)
- [x] Added `[mantis]` optional deps: deepagents>=0.4.1,<0.5.0, langchain-openai>=0.3.0
- [x] Created `MantisConfig` class (SILKROUTE_MANTIS_ prefix) in config/settings.py
- [x] Created `providers/openrouter.py` — ChatOpenAI + OpenRouter base_url adapter
- [x] Created `mantis/agents/code_writer.py` — first Deep Agent with LocalShellBackend
- [x] Rewrote `mantis/runtime/deepagents.py` — delegates to run_code_writer via run_in_executor
- [x] 26 new tests: test_openrouter (11), test_code_writer (9), test_mantis_config (4), test_runtime (+2)
- [x] All 288 tests passing, ruff lint clean, gitleaks clean
- [x] Default runtime remains "legacy" — opt-in via SILKROUTE_RUNTIME=deepagents

## Blockers
None

## Next Handoff
Tomorrow: Phase 2 (FastAPI REST Layer) via planning-prompts | Sonnet builder + Haiku observer | Est: 1 session, ~$3 | Observer notes: LegacyRuntime.stream() still batch-not-stream

## Tech Stack
Python 3.12 (Click + Pydantic + litellm + asyncpg + structlog + Rich + redis + apscheduler + deepagents + langchain-openai) | Next.js 15 (React 19, Tailwind v4) | PostgreSQL 16 | Redis 7 | LiteLLM | Docker Compose

## Session Stats
- New files: 6 (openrouter.py, code_writer.py, agents/__init__.py, 3 test files)
- Modified files: 4 (pyproject.toml, settings.py, deepagents.py, test_runtime.py)
- Tests: 262 existing + 26 new = 288 total, all passing
- Lint: clean (ruff check)
- Security: gitleaks clean, 0 secrets in src/
- Lines: +612

## Links
- GitHub: https://github.com/ScientiaCapital/silkroute
- Vercel: https://silkroute-sepia.vercel.app
- Dashboard (local): http://localhost:3000

---

_Updated by Phase 1 completion. 2026-02-28._
