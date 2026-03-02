# Feature Contract: Phase 9 — Railway Deployment

**Date:** 2026-03-02
**Scope:** STANDARD (5-7 new files, no production code changes)
**Observer:** observer-full (Sonnet)

## Deliverables

| File | Type | Purpose |
|------|------|---------|
| `Dockerfile` | NEW | Multi-stage Docker build (builder + runtime) |
| `scripts/start.sh` | NEW | Container entrypoint (schema init + uvicorn) |
| `railway.toml` | NEW | Railway deployment config |
| `.dockerignore` | NEW | Docker build exclusions |
| `docker-compose.prod.yml` | NEW | Local production testing |

## Architecture Decisions

- **No LiteLLM proxy** — all models route through OpenRouter via litellm Python package
- **API only** — daemon uses Unix sockets (not portable to Railway)
- **Dashboard on Vercel** — already deployed, just needs `NEXT_PUBLIC_API_URL`
- **Schema init via startup script** — `psql -f init.sql` in entrypoint (idempotent DDL)

## Railway Service Topology

```
Railway: silkroute-api (Python 3.12, Dockerfile)
         silkroute-postgres (managed Postgres 16)
         silkroute-redis (managed Redis 7)
Vercel:  silkroute-sepia.vercel.app (Next.js dashboard)
```

## Pre-existing Fixes

- Lint BLOCKER: `test_api_runtime.py:90` — ANN001/ANN202 annotations
- Test fixture cleanup: deduplicate `_make_settings()` across 3 test files

## Verification Criteria

- [ ] All 833+ tests pass
- [ ] `ruff check src/ tests/` clean
- [ ] `docker build -t silkroute-api .` succeeds
- [ ] `/health` returns `{"status":"ok","version":"0.1.0","service":"silkroute-api"}`
- [ ] Observer: 0 BLOCKERs, 0 CRITICALs
