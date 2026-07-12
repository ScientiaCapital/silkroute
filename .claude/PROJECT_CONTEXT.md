# silkroute

**Branch**: main | **Updated**: 2026-07-12

## Status
MCP client bridge built (`src/silkroute/mcp_bridge`) — silkroute can now drive any MCP server over stdio, demonstrated end-to-end against epiphan-mcp-server in a self-hosted Ollama/Qwen2.5 AV demo. model-finops telemetry reporting wired in (opt-in, fire-and-forget). Local Ollama model registry expanded (Qwen2.5, DeepSeek, GLM — two tags flagged unverified). 928 tests passing, lint clean, 0 observer BLOCKERs/CRITICALs (no observer agents run this session — reviewed inline instead).

## Done (This Session — follow-up)
- [x] Telemetry operational closeout: `SILKROUTE_FINOPS_*` added to `.env.example` + passthrough in `docker-compose.prod.yml`'s `api` service (code was already complete both ends)
- [x] Re-verified sender/receiver contract offline: `test_finops_client.py` (6) + model-finops `test_telemetry_endpoint.py` (5) green
- [x] `docs/av-demo-guide.md` finished run-ready — added Telemetry-setup + Dry-run sections (labeled placeholders, no fabricated numbers)
- [x] Resolved Ollama tags via web: `deepseek-r1:14b` REAL (9.0GB/128K); `glm4.6:9b` INVALID (no such tag — GLM-4.6 is ~355B MoE) — both already reflected in `models.py`
- [x] Committed prior-session model-registry/deepseek-v4 work + this closeout as 2 commits, pushed to main

## Blockers
None

## Tomorrow
Tomorrow: `ollama pull qwen2.5:14b` then run `python demo/agent_ready_av_demo.py --mock-pearl --model ollama/qwen2.5:14b` live and paste real output into the guide's Dry-run placeholders | For persisted telemetry: turn on model-finops Supabase + run its `supabase_add_finops_ingest_columns.sql` migration | Observer notes: none run — targeted finish/verify session, 51 affected tests green

## Tech Stack
Python 3.12 (Click + Pydantic + FastAPI + uvicorn + litellm + asyncpg + structlog + Rich + redis + apscheduler + mcp + httpx) | Next.js 15 (React 19, Tailwind v4) | PostgreSQL 16 | Redis 7 | LiteLLM | Docker Compose

## Session Stats
- New files: 8 (mcp_bridge x2, integrations x2, demo x2, docs x1, tests x3)
- Modified files: ~13 (loop.py, router.py, settings.py, models.py, README.md, tests, Backlog.md)
- Tests: 928 passing (up from 913 at session start)
- Lint: clean (ruff check src/ — only 5 pre-existing errors in cli.py/autoresearch, untouched)
- Lines: +1,134 / -62 today
- Commits: 3 (1 feat/build, 1 telemetry feat, 1 prior end-day sync)
- Cost: not separately tracked per-repo — see portfolio total below

## Links
- GitHub: https://github.com/ScientiaCapital/silkroute
- epiphan-mcp-server: https://github.com/ScientiaCapital/epiphan-mcp-server
- model-finops: https://github.com/ScientiaCapital/model-finops

---

_Updated by telemetry-closeout + guide follow-up session. 2026-07-12._
