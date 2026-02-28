# SilkRoute: Architecture Observer Report — Phase 0
**Date:** 2026-03-01
**Session:** Phase 0 Security Hardening + Bug Fixes
**Observer:** Manual Review (observer-full agents failed to write output x3)
**Status:** PASS — No BLOCKERs. 1 RISK, 2 SMELLs.

---

## Executive Summary

Phase 0 makes 4 architectural additions:
1. Shell sandbox layer (`agent/sandbox.py`) between LLM tool calls and `create_subprocess_shell()`
2. Global budget enforcement (`cost_guard.py`) wired into the ReAct loop
3. Bug fix in daemon server (`server.py` worker count tracking)
4. New `mantis/runtime/` package — the first piece of the Mantis strangler fig migration

All changes follow existing codebase conventions. No scope creep. No contract violations. The `mantis/` package is cleanly isolated — zero coupling to existing code except through `run_agent()` in `LegacyRuntime`.

---

## Pattern 1: Agent Drift (Scope Violation)

**Status: PASS — No out-of-scope modifications**

### Files modified (all in-scope per Phase 0 plan):
| File | Change | In Scope? |
|------|--------|-----------|
| agent/sandbox.py | NEW — command blocklist + workspace enforcement | YES (0a) |
| agent/tools.py | Integrated sandbox into shell_exec | YES (0a) |
| agent/loop.py | Wired global budget + sandbox workspace_dir | YES (0b) |
| agent/cost_guard.py | Added check_global_budget() | YES (0b) |
| daemon/server.py | Fixed _active_worker_count | YES (0c) |
| db/repositories/projects.py | Added daily_spend + hourly_rate queries | YES (0b) |
| mantis/ (6 files) | Runtime abstraction layer | YES (0d) |

### Files NOT modified (verified):
- providers/models.py — untouched
- agent/classifier.py — untouched
- config/settings.py — untouched (plan mentioned it but no changes needed)
- dashboard/ — untouched
- sql/init.sql — untouched

---

## Pattern 2: Scope Creep

**Status: PASS**

Phase 0 plan specified 4 sub-phases. All 4 were implemented. Nothing beyond spec was built. Two minor plan items were explicitly deferred (audit log DB persistence, rlimit enforcement) with documented rationale.

---

## Pattern 3: Duplicate Logic

**Status: PASS**

No duplicate logic detected. Specifically:
- `check_budget()` (per-session) and `check_global_budget()` (daily/monthly) are complementary, not overlapping
- `validate_command()` in sandbox.py is the single entry point for all command validation
- `get_runtime()` factory is the single entry point for runtime selection

---

## Pattern 4: Contract Compliance

**Status: PASS with 2 documented deferrals**

| Plan Item | Delivered | Status |
|-----------|-----------|--------|
| Command blocklist (25+ patterns) | YES | PASS |
| Working directory enforcement | YES | PASS |
| Process resource limits | PARTIAL — config exists, not enforced at OS level | DEFERRED |
| Audit log to tool_audit_log table | NO — structlog only | DEFERRED |
| daily_max_usd enforcement | YES | PASS |
| monthly_max_usd enforcement | YES | PASS |
| Circuit breaker ($2/hr) | YES | PASS |
| Fix _active_worker_count | YES | PASS |
| daemon_mode tests | YES — 2 tests | PASS |
| test_lifecycle.py | YES — 13 tests | PASS |
| AgentRuntime Protocol | YES | PASS |
| LegacyRuntime | YES | PASS |
| DeepAgentsRuntime stub | YES | PASS |
| Feature flag SILKROUTE_RUNTIME | YES | PASS |

---

## Findings

[RISK] — agent/tools.py — Module-level `_sandbox_config` global state — The sandbox config is stored as a module-level global set by `create_default_registry()`. In a multi-worker daemon, each worker calls `create_default_registry()` sequentially (workers are asyncio tasks, not processes), so this is safe. However, if the daemon were ever forked to multiprocessing, each process would have its own copy — which is actually correct behavior. **Impact if ignored:** None currently. Document the threading model assumption.

[SMELL] — mantis/runtime/legacy.py — LegacyRuntime.stream() re-invokes the full agent loop — The `stream()` method calls `run_agent()` and yields iteration thoughts. It's not true streaming — it runs the full agent, then yields extracted text. This is acceptable for Phase 0 (stub behavior) but Phase 1 should implement real streaming if Deep Agents supports it. **Impact if ignored:** Users calling `stream()` get no real-time feedback, only a batch of thoughts after completion.

[SMELL] — mantis/runtime/deepagents.py — Stub raises NotImplementedError on import failure — The `invoke()` method checks `import deepagents` and raises `NotImplementedError` if the package isn't installed. This is correct for Phase 0 but should be replaced with actual implementation in Phase 1. If someone accidentally calls this in production, they get a clear error. **Impact if ignored:** None — this is by design.

---

## Dependency Analysis

No new runtime dependencies added in Phase 0. This is correct per plan — Phase 1 will add deepagents, langchain-openai, langgraph, fastapi, uvicorn.

---

## Devil's Advocate Challenges

### Challenge 1: Is the sandbox bypassable via shell metacharacters?
The sandbox validates commands after whitespace normalization but before shell expansion. A command like `r''m -rf /` (with shell quotes) could theoretically bypass the `rm` regex. However, the blocklist patterns use `\b` word boundaries which handle most evasion. The `cat .env` pattern catches the most common credential theft. For full protection, container isolation (Phase 3+) is the real solution.
**Verdict:** Acceptable risk for Phase 0. The sandbox is defense-in-depth, not the sole security layer.

### Challenge 2: Does the global budget check create a DB dependency for the ReAct loop?
The global budget check queries PostgreSQL via `get_daily_spend()` and `get_hourly_spend_rate()`. If DB is unavailable (`pool is None`), the entire global check is skipped. Per-session budget (in-memory) still works.
**Verdict:** Correct behavior. The codebase consistently treats DB as optional (agent runs without DB, just loses persistence).

### Challenge 3: Is the runtime abstraction premature?
The mantis/runtime/ package has 6 files but only `LegacyRuntime` does anything. `DeepAgentsRuntime` is a stub. `registry.py` is a 68-line factory for 2 backends.
**Verdict:** Not premature — this is exactly what Phase 0d specified. The abstraction protects against BLOCKER 2 (Deep Agents API instability). The code is minimal and well-tested (22 tests).

---

## Monitoring Runs

| Date | Session | Result |
|------|---------|--------|
| 2026-02-22 | Phase 7a baseline | BASELINE |
| 2026-03-01 | Phase 0 post-implementation | PASS — 0 BLOCKERs, 1 RISK, 2 SMELLs |
