# SilkRoute: Architecture Observer Report
**Date:** 2026-03-02
**Phase:** 9 — Railway Deployment

## Railway Deployment Topology

```
Railway Project: silkroute
├── silkroute-api       (Python 3.12 — Dockerfile, multi-stage build)
│   ├── /health         Liveness probe (always succeeds)
│   ├── /health/ready   Readiness probe (checks Redis + Postgres)
│   └── Uvicorn w/ --factory, single worker, $PORT env
├── silkroute-postgres  (Railway managed Postgres 16)
│   └── Schema init via psql -f init.sql on startup
└── silkroute-redis     (Railway managed Redis 7)

Vercel (existing, unchanged)
└── silkroute-sepia.vercel.app  (Next.js dashboard)
    └── NEXT_PUBLIC_API_URL → https://<railway-domain>
```

## Architecture Decisions

| Decision | Choice | Rationale |
|----------|--------|-----------|
| LiteLLM proxy | Excluded | OpenRouter handles routing; litellm Python lib is sufficient |
| Daemon | Excluded | Unix socket IPC not portable; API is service boundary |
| Dashboard | Stays on Vercel | Already deployed; just needs env var update |
| Schema init | Startup script | `psql -f init.sql` idempotent, runs every deploy |
| Port binding | `$PORT` env var | Railway assigns port dynamically |

## Dockerfile Design

- **Multi-stage:** Builder compiles hatchling wheel; runtime has only installed packages
- **Non-root:** `silkroute` user created, `USER silkroute` before EXPOSE
- **Healthcheck:** `curl -f http://localhost:$PORT/health` with 30s interval
- **Signal forwarding:** `exec uvicorn` ensures SIGTERM reaches the process

## Test Fixture Cleanup

- `test_lifespan.py`: Consolidated `_make_settings()` → conftest `test_settings` fixture
- `test_cli.py`: Consolidated `_make_test_settings()` → conftest `test_settings` fixture
- `test_api_runtime.py`: Kept local `fake_redis_client` (async/sync fixture mismatch)

## Cost Estimate

Railway Hobby plan: ~$11-15/month (API service + managed Postgres + managed Redis)
