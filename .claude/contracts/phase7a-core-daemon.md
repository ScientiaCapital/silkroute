# Feature Contract: Phase 7a — Core Daemon Mode

**Date:** 2026-02-22
**Scope:** FULL (new architecture, >10 files, new package)

## IN SCOPE

- `src/silkroute/daemon/` package (5 new modules + `__init__.py`)
- `daemon/queue.py` — TaskRequest, TaskResult dataclasses, TaskQueue class
- `daemon/heartbeat.py` — HeartbeatTicker with periodic structlog emission
- `daemon/worker.py` — worker_loop coroutine, execute_task wrapping run_agent()
- `daemon/lifecycle.py` — startup/shutdown orchestration, PID file, DaemonContext
- `daemon/server.py` — DaemonServer, Unix socket listener, signal handling
- 4 new test files: test_daemon_queue, test_daemon_heartbeat, test_daemon_worker, test_daemon_server
- CLI wiring: `silkroute daemon` group with start/submit/status/stop subcommands
- `daemon_mode` flag in `run_agent()` — suppress Rich, use structlog
- `socket_path` and `pid_file` fields in DaemonConfig
- PID file locking (prevent double-start)
- Unix domain socket for IPC (JSON protocol)
- Graceful shutdown (SIGINT/SIGTERM)

## OUT OF SCOPE

- Redis-backed queue (Phase 7b)
- APScheduler / cron jobs (Phase 7b)
- GitHub webhooks (Phase 7 Full)
- REST API / HTTP control plane (Phase 7 Full)
- WebSocket for dashboard (Phase 7 Full)
- Background daemonization (fork/detach) — foreground only
- New pip dependencies — pure asyncio + stdlib
- Budget alert webhooks

## Interfaces

### Unix Socket Protocol (JSON)
```json
// Submit task
{"action": "submit", "task": {"task": "...", "project_id": "default", ...}}
// Response: {"ok": true, "id": "<uuid>"}

// Status query
{"action": "status"}
// Response: {"running": true, "pending": N, "active": N, "completed": N, ...}

// Stop daemon
{"action": "stop"}
// Response: {"ok": true}
```

### CLI Commands
- `silkroute daemon [-f]` — start daemon (foreground)
- `silkroute daemon submit "task" [--project P] [--tier T]` — submit task
- `silkroute daemon status` — query daemon status
- `silkroute daemon stop` — graceful shutdown

## Observer Checkpoints
- [ ] Architecture Observer approves contract
- [ ] Code Quality Observer runs after each phase merge
- [ ] Final Observer report before completion
