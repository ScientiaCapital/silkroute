# silkroute

**Branch**: main | **Updated**: 2026-07-12

## Status
MCP client bridge built (`src/silkroute/mcp_bridge`) — silkroute can now drive any MCP server over stdio, demonstrated end-to-end against epiphan-mcp-server in a self-hosted Ollama/Qwen2.5 AV demo. model-finops telemetry reporting wired in (opt-in, fire-and-forget). Local Ollama model registry expanded (Qwen2.5, DeepSeek, GLM — two tags flagged unverified). 928 tests passing, lint clean, 0 observer BLOCKERs/CRITICALs (no observer agents run this session — reviewed inline instead).

## Done (This Session)
- [x] `src/silkroute/mcp_bridge/client.py` — real MCP stdio client (`connect_mcp_server`), first one in this repo
- [x] Registered `ollama/qwen2.5:14b`/`:32b` as local models; fixed dead `SILKROUTE_OLLAMA_BASE_URL` (was never read — litellm needs `base_url=`, not `api_base=`)
- [x] `demo/pearl_mock_server.py` + `demo/agent_ready_av_demo.py` — verified end-to-end against real, unmodified epiphan-mcp-server
- [x] `src/silkroute/integrations/finops_client.py` — fire-and-forget usage reporting to model-finops, `FinopsConfig` settings
- [x] Caught + fixed 2 real bugs: finops report was scheduled after `pool is None` guard (would never fire during `--mock-pearl`); used `SilkRouteSettings()` instead of `FinopsConfig()` directly (triggered unrelated provider-required validator)
- [x] Added DeepSeek + current-gen GLM local Ollama entries (flagged unverified — no internet access to confirm real tags)
- [x] `docs/av-demo-guide.md` — model selection, dashboard reality check ($0.00 cost is correct, not a bug)
- [x] Verified real HTTP contract with model-finops's new telemetry endpoint (uvicorn + unmocked client call)
- [x] Committed as `36a3ac3`, `4d5dde2`

## Blockers
None

## Tomorrow
Tomorrow: `ollama pull qwen2.5:14b` (or verify `deepseek-r1:14b`/`glm4.6:9b` tags first via `ollama search`) then run `python demo/agent_ready_av_demo.py --mock-pearl` live | Turn on model-finops + Supabase to test telemetry end-to-end for real | Observer notes: none run this session — consider spawning formal observer agents next session given the scope of changes

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

_Updated by AV demo + telemetry session. 2026-07-12._
