# Phase 5: Skills + Context7 + Tools — Feature Contract

**Date:** 2026-03-01 | **Scope:** FULL | **Observer:** observer-lite (Haiku)

## IN SCOPE
- `mantis/skills/` package (models, registry, context7 client, 4 built-in skills)
- `mantis/context/` package (ContextManager with versioning and scoping)
- SkillsConfig + Context7Config in `config/settings.py`
- 4 new agent tools: `http_request`, `search_grep`, `git_ops`, `env_info`
- LLMDecomposer replacing KeywordDecomposer (W4 fix) with fallback
- API: GET /skills, GET /skills/{id}, POST /context7/resolve, POST /context7/query
- CLI: `silkroute skills list|info`, `silkroute context7 resolve|query`
- `skill_executions` DB table for analytics
- Backlog: W1 (narrow except in ralph), W2 (visible checkpoint failures)
- ~80 new tests

## OUT OF SCOPE
- Dashboard skills UI (Phase 6)
- MCP protocol bridge (future)
- Custom user-defined skills (future — only built-in for now)
- WebSocket live streaming for skills
- Skill marketplace or remote loading

## SUCCESS CRITERIA
- [ ] All 493 existing tests still pass
- [ ] ~80 new tests pass
- [ ] GET /skills returns skill catalog
- [ ] POST /context7/query returns library docs
- [ ] LLMDecomposer correctly splits compound tasks
- [ ] New tools (http_request, search_grep, git_ops, env_info) work in agent loop
- [ ] ContextManager preserves context across supervisor steps
- [ ] Backlog W1/W2/W4 resolved
- [ ] ruff clean, 0 observer BLOCKERs/CRITICALs
