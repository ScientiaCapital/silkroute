# silkroute

**Branch**: main | **Updated**: 2026-03-22

## Status
Phase 10 (AutoResearch Engine) complete on `main`. Autonomous experiment loop using Chinese LLMs as researchers — modify code, run eval, keep/discard, loop forever. Inspired by Karpathy's autoresearch. 879 tests passing, lint clean, 0 observer BLOCKERs/CRITICALs. All Phases 0-10 complete.

## Done (This Session — Phase 10)
- [x] `src/silkroute/autoresearch/` — 10 new files, autonomous experiment engine
- [x] ResearchTarget protocol + Metrics dataclass + Ledger TSV tracking
- [x] LLM interaction via existing `create_openrouter_model()` (no new deps)
- [x] CodeImproverTarget: pytest + coverage + ruff eval, composite scoring
- [x] Engine: git branch isolation, 50-line diff cap, crash circuit breaker, signal handlers
- [x] CLI: `silkroute research start/status/results` commands
- [x] programs/code.md — Karpathy-style instructions for the LLM researcher
- [x] 26 new tests, all passing
- [x] DA Gate 1 + Gate 2: CLEAN (0 blockers, 0 warnings)
- [x] DA fix: scoped `git add` to specific files (not `-A`)
- [x] Security sweep: 0 secrets found
- [x] Committed as `f00f1dc`

## Blockers
None

## Tomorrow
Tomorrow: Test autoresearch end-to-end with real Chinese LLM (DeepSeek V3.2 via OpenRouter) — run `silkroute research start --target code --max-experiments 3` and verify the loop works | Consider adding Prompt Lab target (#25) or Routing Optimizer (#26) | Observer notes: Backlog #24 — pytest runs 3x per experiment (optimization opportunity)

## Tech Stack
Python 3.12 (Click + Pydantic + FastAPI + uvicorn + litellm + asyncpg + structlog + Rich + redis + apscheduler + deepagents + langchain-openai + httpx) | Next.js 15 (React 19, Tailwind v4) | PostgreSQL 16 | Redis 7 | LiteLLM | Docker Compose | Railway

## Session Stats
- New files: 13 (10 autoresearch + 1 test + 2 observer archives)
- Modified files: 5 (cli.py, Backlog.md, observer reports, alerts)
- Tests: 879 passing (up from 842), 26 new
- Lint: clean (ruff check)
- Lines: +1,647
- Observer: 0 BLOCKER, 0 CRITICAL, 0 WARNING
- Commits: 1 feat
- Cost: ~$8-10 estimated

## Links
- GitHub: https://github.com/ScientiaCapital/silkroute
- Karpathy's autoresearch: https://github.com/karpathy/autoresearch
- Vercel: https://silkroute-sepia.vercel.app
- Dashboard (local): http://localhost:3000
- API docs (local): http://localhost:8787/docs

---

_Updated by Phase 10 completion. 2026-03-22._
