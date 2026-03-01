# silkroute

**Branch**: main | **Updated**: 2026-03-01

## Status
Phase 5 (Skills + Context7 + Tools) complete on `main`. Skills framework with 5 built-in skills, Context7 REST client, ContextManager with scoping/versioning, LLMDecomposer, 4 new agent tools (http_request, search_grep, git_ops, env_info), API endpoints, CLI commands, skill_executions DB table, 3 backlog fixes (W1/W2/W4). 691/693 tests passing (2 pre-existing: deepagents optional dep). Lint clean. 0 observer BLOCKERs/CRITICALs.

## Done (This Session --- Phase 5)
- [x] Created `mantis/skills/` package: models, registry, context7, builtin/ (5 skills)
- [x] Created `mantis/context/` package: models, manager (scoped, versioned, token-aware)
- [x] LLMDecomposer with LRU cache + KeywordDecomposer fallback (W4 fix)
- [x] 4 new tools in agent/tools.py: http_request (SSRF-safe), search_grep, git_ops (allowlist), env_info (secret-filtered)
- [x] SkillsConfig + Context7Config in settings.py
- [x] API: GET /skills, GET /skills/{id}, POST /context7/resolve, POST /context7/query
- [x] CLI: silkroute skills list|info, silkroute context7 resolve|query
- [x] skill_executions DB table + indexes
- [x] Backlog W1: narrowed except in ralph.py
- [x] Backlog W2: visible checkpoint failures (log.warning)
- [x] Backlog W4: LLMDecomposer replaces KeywordDecomposer
- [x] ~200 new tests (691 total), ruff clean, gitleaks clean

## Blockers
None

## Tomorrow
Tomorrow: Phase 6 (Multi-project + Dashboard) via planning-prompts | Sonnet builder + Haiku observer | Est: 2-3 sessions, ~$8 | Observer notes: SSRF dual-impl drift risk, ContextManager not yet wired into SupervisorRuntime, skill_executions repo missing

## Tech Stack
Python 3.12 (Click + Pydantic + FastAPI + uvicorn + litellm + asyncpg + structlog + Rich + redis + apscheduler + deepagents + langchain-openai + httpx) | Next.js 15 (React 19, Tailwind v4) | PostgreSQL 16 | Redis 7 | LiteLLM | Docker Compose

## Session Stats
- New files: 21 (12 source + 9 test)
- Modified files: 13 (11 source + 1 test + 1 meta)
- Tests: 493 existing + ~200 new = 691 passing (2 pre-existing failures)
- Lint: clean (ruff check)
- Security: gitleaks clean, 0 secrets
- Lines: +4,008 new code, +810/-20 modified
- Observer: 0 BLOCKER, 0 CRITICAL, 1 WARNING (logged to Backlog)

## Links
- GitHub: https://github.com/ScientiaCapital/silkroute
- Vercel: https://silkroute-sepia.vercel.app
- Dashboard (local): http://localhost:3000
- API docs (local): http://localhost:8787/docs

---

_Updated by Phase 5 completion. 2026-03-01._
