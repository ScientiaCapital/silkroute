# SilkRoute: Architecture Observer Report — Phase 7a
**Date:** 2026-02-22
**Session:** Phase 7a Core Daemon Mode — Pre-implementation baseline
**Observer:** Observer Full (Sonnet 4.6)
**Status:** BASELINE — Contract approved with conditions. Implementation not started.

---

## Executive Summary

The Phase 7a contract is well-formed and appropriately scoped. The existing codebase is a solid foundation: asyncpg pool, structlog throughout, clean dataclass/StrEnum patterns, and a working ReAct agent loop. No out-of-scope changes have been made. No scope creep is detectable at baseline.

Four architectural concerns must be addressed during implementation:

1. The `daemon` CLI command in `cli.py` is currently a stub that must be replaced with a proper Click group (`@main.group()`). The stub and the group cannot coexist.
2. `run_agent()` in `loop.py` is tightly coupled to Rich console output. The `daemon_mode` flag must suppress all `console.print()` / `Console()` usage — this requires threading a boolean parameter through multiple call sites.
3. The DaemonConfig in `settings.py` is missing `socket_path` and `pid_file` fields required by the contract.
4. The Unix socket protocol in the contract is JSON over a raw Unix domain socket. The implementation must choose a framing protocol (length-prefixed or newline-delimited) — the contract does not specify, which is a gap.

---

## Pattern 1: Agent Drift (Scope Violation)

**Status: PASS — No out-of-scope modifications**

`git diff --name-only main...HEAD` returned no output. Branch is at main. All Phase 3 deliverables are committed.

The Phase 7a contract lists these files to be created or modified:

| Deliverable | File | Pre-impl Status |
|-------------|------|-----------------|
| Daemon package | `src/silkroute/daemon/__init__.py` | MISSING (expected) |
| Task queue | `src/silkroute/daemon/queue.py` | MISSING (expected) |
| Heartbeat | `src/silkroute/daemon/heartbeat.py` | MISSING (expected) |
| Worker loop | `src/silkroute/daemon/worker.py` | MISSING (expected) |
| Lifecycle | `src/silkroute/daemon/lifecycle.py` | MISSING (expected) |
| IPC server | `src/silkroute/daemon/server.py` | MISSING (expected) |
| CLI wiring | `src/silkroute/cli.py` (modified) | stub exists at line 191-200 |
| daemon_mode flag | `src/silkroute/agent/loop.py` (modified) | NOT STARTED |
| DaemonConfig fields | `src/silkroute/config/settings.py` (modified) | socket_path / pid_file MISSING |
| Test: queue | `tests/test_daemon_queue.py` | MISSING (expected) |
| Test: heartbeat | `tests/test_daemon_heartbeat.py` | MISSING (expected) |
| Test: worker | `tests/test_daemon_worker.py` | MISSING (expected) |
| Test: server | `tests/test_daemon_server.py` | MISSING (expected) |

No files outside this list are expected to change. If any of the following files are modified, flag immediately:

- `src/silkroute/providers/models.py` — out of scope
- `src/silkroute/agent/classifier.py` — out of scope
- `src/silkroute/agent/tools.py` — out of scope
- `src/silkroute/db/` (any file) — out of scope unless pool.py race condition fix
- `dashboard/` — out of scope
- `sql/init.sql` — out of scope (no new tables for Phase 7a)

---

## Pattern 4: Scope Creep

**Status: PASS (baseline — nothing implemented yet)**

### Out-of-Scope Items Explicitly Listed in Contract

The following are deferred to Phase 7b or Phase 7 Full. Any appearance in Phase 7a code is a **[BLOCKER]**:

| Out-of-Scope Item | Why Flagged |
|-------------------|-------------|
| Redis-backed queue | Phase 7b — queue.py must use `asyncio.Queue`, not Redis |
| APScheduler / cron | Phase 7b — no scheduled tasks in Phase 7a |
| GitHub webhooks | Phase 7 Full — no HTTP server, no webhook handlers |
| REST API / HTTP control plane | Phase 7 Full — Unix socket only |
| WebSocket for dashboard | Phase 7 Full |
| Background fork/detach | Explicitly excluded — foreground only |

### Scope Creep Risk: cli.py Daemon Stub

**File:** `src/silkroute/cli.py:191-200`

The current `daemon` command is registered as `@main.command()`. The contract requires it to become `@main.group()` with four subcommands: `start`, `submit`, `status`, `stop`. Changing `@main.command()` to `@main.group()` on the same name will work but is a semantic replacement — the old "daemon mode not yet implemented" message must be removed entirely.

```
[INFO] — src/silkroute/cli.py:191 — daemon() is currently a plain @main.command()
  that prints "not yet implemented". It must be replaced with a @main.group()
  and four subcommands. The stub body (lines 193-199) must be deleted.
  Verify the group's invoke_without_command behavior: calling `silkroute daemon`
  with no subcommand should show help, not error.
```

---

## Pattern 7: Contract Drift

**Status: GAPS IDENTIFIED — must be resolved during implementation**

### 7a. DaemonConfig Missing Required Fields

**Severity: [BLOCKER]**

The contract specifies:
> `socket_path` and `pid_file` fields in DaemonConfig

`src/silkroute/config/settings.py:127-144` — `DaemonConfig` currently has:
- `enabled` — present
- `heartbeat_interval_seconds` — present
- `webhook_port` — present (out of scope for Phase 7a, but pre-existing)
- `max_concurrent_sessions` — present
- `nightly_scan_enabled` — present (out of scope)
- `nightly_scan_cron` — present (out of scope)
- `dependency_check_cron` — present (out of scope)

Missing:
- `socket_path: str` — path to Unix domain socket (e.g., `~/.silkroute/daemon.sock`)
- `pid_file: str` — path to PID lockfile (e.g., `~/.silkroute/daemon.pid`)

These must be added as `Field(default=...)` entries with `SILKROUTE_DAEMON_` prefix so they are overridable via environment variable.

**Required action:** Add both fields to `DaemonConfig` with sensible defaults using `Path` expansion.

### 7b. run_agent() daemon_mode Flag

**Severity: [BLOCKER]**

The contract specifies:
> `daemon_mode` flag in `run_agent()` — suppress Rich, use structlog

`src/silkroute/agent/loop.py:37-46` — current `run_agent()` signature:
```python
async def run_agent(
    task: str,
    *,
    model_override: str | None = None,
    tier_override: str | None = None,
    project_id: str = "default",
    max_iterations: int = 25,
    budget_limit_usd: float = 10.0,
    workspace_dir: str | None = None,
) -> AgentSession:
```

Missing: `daemon_mode: bool = False`

Rich output calls appear at lines: 60-67, 73, 143-146, 150, 155, 159, 207-209, 218, 231, 239, 287-294.

Every `console.print()` call in `run_agent()` must be guarded by `if not daemon_mode:`. Alternatively, a `no_color=True` Console with `stderr=True` can be used in daemon mode to redirect to stderr. The simpler approach: gate on `daemon_mode`.

**Required action:** Add `daemon_mode: bool = False` parameter. All `console.print()` calls in the loop body must be suppressed when `daemon_mode=True`. structlog calls (`log.info`, `log.warning`, `log.error`) are already present and should be the sole output channel in daemon mode. The `_make_console()` pattern or a simple `if not daemon_mode:` gate is acceptable.

### 7c. Unix Socket Protocol — Framing Unspecified

**Severity: [WARNING]**

The contract defines the JSON messages but does not specify the framing protocol for the Unix domain socket:

```json
{"action": "submit", "task": {...}}
{"ok": true, "id": "<uuid>"}
```

Unix domain sockets are stream-based (like TCP). A single `socket.recv()` call does not guarantee a complete JSON message — bytes can arrive fragmented. Two valid approaches:

**Option A: Newline-delimited JSON (NDJSON)**
- Sender writes `json.dumps(msg) + "\n"`
- Receiver reads until `\n`
- Simple, human-readable, works for the message sizes in this protocol

**Option B: 4-byte length prefix**
- Sender writes `struct.pack(">I", len(data)) + data`
- Receiver reads 4 bytes for length, then exactly that many bytes
- More robust for large messages

**Recommendation:** Use newline-delimited JSON. The largest message (submit) is under 1KB — well within a single kernel buffer for Unix domain sockets. Document the framing choice in `daemon/server.py` module docstring.

**Required action:** Choose a framing protocol, document it in the contract or server module, and verify both client (CLI submit/status/stop) and server use the same framing.

### 7d. CLI Protocol — Client Code Location

**Severity: [WARNING]**

The `silkroute daemon submit`, `silkroute daemon status`, and `silkroute daemon stop` subcommands must connect to the daemon's Unix socket and send JSON commands. The contract specifies these as CLI commands but does not specify where the client connection code lives.

Two options:
1. Implement a minimal client function in `daemon/server.py` (e.g., `send_command(action, payload)`)
2. Implement inline in `cli.py` subcommand handlers

**Recommendation:** A `send_command()` utility in `daemon/server.py` (or a `daemon/client.py` if it grows large). This keeps `cli.py` thin and allows the client logic to be unit-tested.

If a `daemon/client.py` is created, it must be listed as in-scope (it is not currently in the contract — this would be a minor scope addition that is architecturally justified).

### 7e. PID File Locking — Double-Start Detection

**Severity: [WARNING]**

The contract specifies:
> PID file locking (prevent double-start)

The correct pattern is:
1. Attempt exclusive creation of the PID file (`O_CREAT | O_EXCL`)
2. Write current PID
3. On startup: check if PID file exists AND the PID in it is a running process
4. On shutdown: remove PID file

Edge case: if the daemon crashes without cleanup, the stale PID file must not prevent restart. The implementation must handle:
- PID file exists, but `os.kill(pid, 0)` raises `ProcessLookupError` → stale, safe to overwrite
- PID file exists and process is running → double-start, must exit with error message

**Required action:** Implement `lifecycle.py` startup with this exact stale-PID logic. A test case in `test_daemon_server.py` should verify the stale PID scenario.

### 7f. Graceful Shutdown — Signal Handler Scope

**Severity: [INFO]**

The contract specifies:
> Graceful shutdown (SIGINT/SIGTERM)

In an asyncio application, signal handlers must be registered using `loop.add_signal_handler()` (not `signal.signal()`), because `signal.signal()` handlers run in the main thread synchronously, which can interrupt async tasks. The correct pattern:

```python
loop = asyncio.get_event_loop()
loop.add_signal_handler(signal.SIGINT, shutdown_callback)
loop.add_signal_handler(signal.SIGTERM, shutdown_callback)
```

The shutdown sequence must:
1. Stop accepting new connections
2. Signal all workers to drain (no new tasks accepted)
3. Wait for in-flight `run_agent()` calls to complete (or timeout after N seconds)
4. Cancel the heartbeat ticker
5. Close the asyncpg pool (`close_pool()`)
6. Remove the PID file

The `close_pool()` deferred issue from Phase 3 Challenge 2 is now active — Phase 7a must call `await close_pool()` in the shutdown sequence.

---

## Devil's Advocate Challenges

### Challenge 1: Does daemon/server.py need to be a separate module?

**File:** Contract line 8 — `daemon/server.py`

**Concern:** The Unix socket server has a well-defined responsibility (accept connections, dispatch JSON commands). However, the server, worker, and queue are tightly interdependent — the server needs access to the queue to submit tasks, and the lifecycle module needs access to both. This creates a dependency web that could have all lived in a single `daemon.py` module.

**Counter-argument:** The 5-module split matches the project's established pattern (each concern in its own module). `agent/` has 6 modules. `db/` has pool + 3 repositories. The split is consistent with conventions.

**Assessment:** The split is justified. But ensure `daemon/__init__.py` exports a clean public API so `cli.py` imports from `silkroute.daemon` rather than reaching into `silkroute.daemon.server` directly.

### Challenge 2: Is asyncio.Queue sufficient, or will it block the event loop?

**File:** Contract line 9 — `daemon/queue.py` — `TaskQueue class`

**Concern:** `asyncio.Queue` is an in-memory, event-loop-bound queue. The contract defers Redis to Phase 7b. But there is a subtle risk: if `worker_loop` calls `asyncio.Queue.get()` and then immediately calls `await run_agent()`, the queue drains but the worker is blocked on the agent for potentially several minutes. With `max_concurrent_sessions = 3`, three workers each block for the duration of their agent run. If the queue fills (more than 3 pending tasks), new submits block.

The contract's `asyncio.Queue` approach handles this correctly if the worker loop is implemented as multiple concurrent tasks:
```python
# Correct: spawn max_concurrent_sessions worker tasks
workers = [asyncio.create_task(worker_loop(queue)) for _ in range(max_concurrent)]
```

**Assessment:** The `asyncio.Queue` approach is correct for Phase 7a. The concern is valid only if workers are implemented as a single sequential loop. Verify the worker implementation uses `asyncio.gather()` or `asyncio.create_task()` to spawn concurrent worker coroutines.

### Challenge 3: Does HeartbeatTicker need to be a class?

**File:** Contract line 10 — `daemon/heartbeat.py` — `HeartbeatTicker`

**Concern:** A "heartbeat" is just a coroutine that sleeps in a loop and emits a log event. A simple async function is sufficient:
```python
async def heartbeat_loop(interval_seconds: int) -> None:
    while True:
        log.info("daemon_heartbeat", uptime_seconds=...)
        await asyncio.sleep(interval_seconds)
```

A class adds lines of code with no additional behavior unless the heartbeat needs state (e.g., tracking uptime, tracking completed task counts). If the heartbeat emits `pending_tasks` and `active_tasks` counts, it needs access to the queue — in which case a class that accepts the queue in `__init__` is cleaner than a function with multiple parameters.

**Assessment:** Use a class if the heartbeat emits queue metrics (the contract says "periodic structlog emission" but does not specify what fields). A class that takes the queue as a dependency and emits `{"pending": N, "active": N, "uptime_s": N}` is the better design. A bare function is insufficient for useful heartbeat data.

### Challenge 4: Should the socket path default to /tmp or ~/.silkroute/?

**File:** `src/silkroute/config/settings.py:127` — `DaemonConfig`

**Concern:** The `socket_path` field's default location matters for security and usability.

- `/tmp/silkroute.sock` — world-accessible in `/tmp`, vulnerable to symlink attacks, swept on reboot
- `~/.silkroute/daemon.sock` — user-owned, persistent across reboots, survives process crashes

On macOS (the primary dev platform per `SILKROUTE_HARDWARE_PROFILE=mac-mini` default), `/tmp` is actually a symlink to `/private/tmp` and has sticky-bit set. The risk is lower than on Linux. However, `~/.silkroute/daemon.sock` is unambiguously more secure.

**Recommendation:** Default to `~/.silkroute/daemon.sock`. The `init` command already creates `~/.silkroute/` directories. The socket file will co-locate with session logs.

**Required action:** Ensure `lifecycle.py` creates `~/.silkroute/` if it does not exist before binding the socket.

### Challenge 5: The `daemon` CLI command replacement is a breaking change

**File:** `src/silkroute/cli.py:191`

**Concern:** The current `@main.command("daemon")` will be replaced by `@main.group("daemon")`. This is a backward-incompatible change: `silkroute daemon` currently prints a stub message. After Phase 7a, `silkroute daemon` with no subcommand shows help. Any scripts or tests calling `silkroute daemon` directly will get different behavior.

**Assessment:** There are currently no tests for `silkroute daemon` (the stub is not tested). There are no scripts relying on the stub output. The transition is safe. But verify `invoke_without_command=True` is not set on the group — the default (show help on bare invocation) is the correct behavior for a daemon group command.

---

## Contract Compliance

| Contract Requirement | Status | Severity |
|---------------------|--------|----------|
| `daemon/__init__.py` | MISSING | BASELINE |
| `daemon/queue.py` — TaskRequest, TaskResult, TaskQueue | MISSING | BASELINE |
| `daemon/heartbeat.py` — HeartbeatTicker | MISSING | BASELINE |
| `daemon/worker.py` — worker_loop, execute_task | MISSING | BASELINE |
| `daemon/lifecycle.py` — startup/shutdown, PID file | MISSING | BASELINE |
| `daemon/server.py` — DaemonServer, Unix socket | MISSING | BASELINE |
| `socket_path` field in DaemonConfig | MISSING | [BLOCKER] |
| `pid_file` field in DaemonConfig | MISSING | [BLOCKER] |
| `daemon_mode` flag in `run_agent()` | MISSING | [BLOCKER] |
| `silkroute daemon start/submit/status/stop` CLI | Stub only | [BLOCKER] |
| PID file locking (prevent double-start) | MISSING | BASELINE |
| Unix domain socket JSON protocol | MISSING | BASELINE |
| Graceful shutdown (SIGINT/SIGTERM) | MISSING | BASELINE |
| 4 test files for daemon modules | MISSING | BASELINE |
| No new pip dependencies | PASS (0 added) | — |
| Framing protocol for Unix socket | NOT SPECIFIED in contract | [WARNING] |
| close_pool() called in shutdown | NOT STARTED | [WARNING] |

---

## Monitoring Runs

| Date | Time | Session | Result |
|------|------|---------|--------|
| 2026-02-22 | 01:41 UTC | Phase 3 pre-implementation baseline | BLOCKERS — incomplete implementation |
| 2026-02-22 | 17:27 UTC | Phase 7a pre-implementation baseline | BASELINE — contract approved with conditions |
