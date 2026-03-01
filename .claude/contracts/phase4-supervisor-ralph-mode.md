# Phase 4: Supervisor + Ralph Mode — Feature Contract

**Date**: 2026-02-28 | **Scope**: FULL | **Observer**: observer-full

## IN SCOPE
- `mantis/supervisor/` package (models, runtime, ralph, `__init__`)
- SupervisorRuntime implementing AgentRuntime Protocol
- SupervisorPlan with sequential/conditional step execution
- Inter-step context passing via `plan.context[step_id]`
- Checkpoint persistence to `supervisor_sessions` table
- Retry logic with exponential backoff
- Ralph Mode autonomous loop via DaemonScheduler cron
- 3 new middleware: RetryMiddleware, CheckpointMiddleware, AlertMiddleware
- New `supervisor_sessions` DB table + repository
- SupervisorConfig in settings.py
- API: POST/GET/DELETE `/supervisor/sessions`, POST `.../resume`
- CLI: `silkroute supervisor` command group
- Backlog: W1 narrow except, W2 atomic budget, R2 parallel streaming, W3 immutable allocate

## OUT OF SCOPE
- LLM-based plan generation (Phase 5)
- Dashboard supervisor UI (Phase 6)
- New pip dependencies
- WebSocket live updates
- Inter-agent real-time messaging

## SUCCESS CRITERIA
- [ ] All existing tests still pass
- [ ] ~80 new tests pass
- [ ] POST /supervisor/sessions creates and executes supervisor workflow
- [ ] Checkpoint persists to DB after each step
- [ ] Resume from checkpoint works
- [ ] Retry with backoff on failed steps
- [ ] Ralph Mode runs one autonomous cycle via scheduler
- [ ] Backlog W1/W2/R2/W3 all resolved
- [ ] ruff clean, 0 observer BLOCKERs/CRITICALs
