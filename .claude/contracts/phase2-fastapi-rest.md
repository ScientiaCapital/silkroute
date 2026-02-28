# Feature Contract: Phase 2 — FastAPI REST Layer

## Inputs
- HTTP requests from Next.js dashboard, CLI, or external tools
- Bearer token for authentication (`SILKROUTE_API_KEY` env var)

## Outputs
- REST JSON responses (task IDs, results, model catalog, budget status)
- SSE event stream for runtime streaming

## Invariants
- All existing 288 tests continue passing (zero breaking changes)
- Budget governance enforced on task submission
- No new global mutable state (DI via FastAPI `Depends`)
- Queue backpressure returns 429, not silent failure

## Scope Boundary
- **In scope:** REST endpoints, auth, Pydantic models, lifespan, CLI command, tests
- **Out of scope:** True token-level streaming, WebSocket, user management, rate limiting tiers

## API Surface
| Method | Path | Auth | Purpose |
|--------|------|------|---------|
| GET | /health | No | Version + status |
| GET | /health/ready | No | Redis + DB connectivity |
| POST | /tasks | Yes | Submit task to queue |
| GET | /tasks/{task_id}/result | Yes | Poll for task result |
| GET | /tasks/queue/status | Yes | Queue depth + worker count |
| POST | /runtime/invoke | Yes | Direct runtime invoke (sync) |
| GET | /runtime/stream | Yes | SSE streaming invoke |
| GET | /models | No | Model catalog (filterable) |
| GET | /models/{model_id} | No | Single model detail |
| GET | /budget | Yes | Global budget status |
| GET | /budget/{project_id} | Yes | Per-project budget |

## Architecture
FastAPI runs as a separate process from DaemonServer, sharing Redis for
queue operations and the DB pool for budget queries.
