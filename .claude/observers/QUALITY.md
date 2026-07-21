# Code Quality Audit — silkroute

**Date:** 2026-07-21T20:28:55Z (updated after full-suite bisection)
**Session:** Observer Full — DA review of edge/openav plan (branch feat/edge-mantis-models-openav, uncommitted)
**Status:** BLOCKERS FOUND (2)

---

## Findings

[BLOCKER] — `src/silkroute/agent/loop.py:101` — `run_agent()` instantiates a bare, un-mocked
`SilkRouteSettings()` just to read `.hardware_profile`. `SilkRouteSettings` carries a cross-field
`model_validator` (`config/settings.py:580` `validate_at_least_one_provider`) that raises
`ValidationError` if no provider key is set and `ollama_enabled` is false. **Confirmed via a full
`pytest` bisection (`git stash` base-commit run vs diff-applied run):**
  - Base commit (pre-diff): **13 failed, 1112 passed** — all 13 confirmed pre-existing/unrelated
    (missing optional `deepagents` package, playbook-artifact drift — see below).
  - Diff applied: **33 failed, 1099 passed** — the same 13, plus **20 new failures**, all in
    `run_agent()`'s own test surface: `tests/test_loop.py::TestRunAgent` (8 tests),
    `TestRunAgentStreaming` (5), `TestRunAgentWithDB` (2), `TestFinopsReporting` (3), plus
    `tests/test_api_demo.py::TestDemoStreamLive` (2, the live-agent-mode `/demo/stream?live=true`
    feature). Every one fails with `pydantic_core._pydantic_core.ValidationError: At least one LLM
    provider must be configured` — i.e. this diff turns virtually the entire agent-loop test suite
    red. In production this specific crash is narrower (the CLI's `run` command, `cli.py:75-104`,
    never sets `--hardware-profile` and calls `run_agent` with none, so it hits this line on every
    invocation — but a real deployment necessarily has a provider key configured to do anything
    useful, so the validator itself would pass there). The test-suite damage is the immediate,
    unambiguous blocker. Every other concern in `run_agent` reads only its narrowly-scoped
    sub-config (`AgentConfig()`, `BudgetConfig()`, `MemoryConfig()`, `MCPConfig()`) — this is the
    only place the loop touches the top-level settings object, and it also re-parses every nested
    `BaseSettings` block (providers, budget, mcp, mantis, api, supervisor, skills, context7) plus
    `.env` on every call that doesn't pass `hardware_profile` explicitly. **Fix:** add a narrow
    accessor (e.g. a module-level `get_hardware_profile()` reading `SILKROUTE_HARDWARE_PROFILE`
    directly, bypassing the full-settings validator) instead of constructing `SilkRouteSettings()`
    inline; re-run the full suite to confirm it returns to 13/1112 (or better).

[BLOCKER] — `src/silkroute/agent/router.py:96-97` — the hardware-fit branch checks only
`PROFILE_RAM_GB` against a profile; it never checks `ProviderConfig.ollama_enabled`
(`config/settings.py:56`). `.env.example` ships `SILKROUTE_HARDWARE_PROFILE=mac-mini` (unchanged
default) and `SILKROUTE_OLLAMA_ENABLED=false` (unchanged default) — the out-of-the-box config for
anyone who `cp .env.example .env` + sets an OpenRouter key. On that default, any FREE/STANDARD task
silently selects a local Ollama model regardless of whether Ollama is installed/running;
`get_litellm_model_string` (`router.py:156-157`) returns the bare model id, and
`litellm.acompletion` fails at request time (`loop.py:290-306`) with a raw connection-refused
error — session `FAILED` at iteration 1, no cloud fallback. Pre-existing for FREE tier; today's
change (`router.py:88-99`, widening `tier != PREMIUM` from `tier == FREE`) doubles the blast
radius to STANDARD — the tier the AV-control classifier uses for routine commands
(`providers/models.py:415-419` comment: "default AV commands classify STANDARD").
`tests/test_hardware_routing.py:75-80`'s renamed `test_standard_runs_local_on_big_box` locks in
the behavior with zero coverage of `ollama_enabled=False`. **Fix:** `best_local_model`/
`select_model` must check `ollama_enabled` (ideally with a fail-fast/reachability check) before
returning a local model; add a test for `hardware_profile` set + `ollama_enabled=False`.

[WARNING] — `src/silkroute/config/settings.py:402-406` — doc comment claims "the full catalog is
only 10 tools" with `ec20_tracking` as the sole exclusion. The actual `epiphan-openav-bridge`
catalog (`openav-mcp/openav_mcp/server.py:39-89`, `_SPECS`) is **12** tools;
`openav_tool_allowlist` (`settings.py:387-400`) lists 9, silently dropping `ec20_jog` and
`ec20_preset_save` too, uncommented. `ec20_jog` is the bridge's own documented *preferred*
framing verb (server.py:62); the allowlist exposes only the "secondary"/"calibrated best-effort"
`ec20_ptz` instead (server.py:60-61, 79). Full writeup + contract-drift framing in `ARCH.md`.

[INFO] — `src/silkroute/config/settings.py:348-357` (`openav_command` default `"python"`) +
`mcp_bridge/client.py:70-74` — if `openav_enabled=true` but `openav_command` is left at the bare
default (not the bridge's own venv path), the subprocess fails (`ModuleNotFoundError: openav_mcp`)
and `connect_mcp_server` swallows it as a `log.warning` — the agent then runs with zero device
tools, no user-facing signal. Both `.env.example` and `docs/edge-deployment.md` correctly instruct
an absolute venv path, so this only bites a user who skips that step. Consider a startup-time
fail-loud check when `openav_enabled=true` and zero tools were registered from that server.

## Metrics

| Metric | Count |
|---|---|
| TODO/FIXME/HACK/XXX/TEMP in changed files | 0 |
| New/modified functions without tests | 0 (diff surface has matching tests) |
| Full-suite result, base commit (pre-diff, `git stash`) | 13 failed, 1112 passed |
| Full-suite result, diff applied | 33 failed, 1099 passed |
| Tests broken by this diff (33 − 13, confirmed via bisection) | **20** — `test_loop.py::{TestRunAgent×8, TestRunAgentStreaming×5, TestRunAgentWithDB×2, TestFinopsReporting×3}`, `test_api_demo.py::TestDemoStreamLive×2` |
| Tests failing pre-existing on base commit (confirmed unrelated) | 13 — 6 `test_room_health_*` (playbook-artifact drift), 4 `test_code_writer.py` + 2 `test_runtime.py` (missing optional `deepagents` package in this env), 1 `test_api_demo.py::TestDemoHeal` |
| Empty catch / bare except in changed files | 0 |
| Unused imports in changed files | 0 |
| New dependencies added | 0 |

## Monitoring Runs

- 2026-07-21T20:28:55Z — Full DA review: read complete diffs of router.py/loop.py/settings.py/
  models.py/.env.example; traced `select_model` → `get_litellm_model_string` →
  `litellm.acompletion` error path; ran the **full** suite twice (`git stash` base vs diff-applied)
  to get an exact before/after failure count rather than trusting a spot-check — this caught the
  true blast radius (20 broken tests, not the 3 a narrower `-k` filter first suggested);
  cross-checked openav-mcp's actual `_SPECS` tool catalog against the SilkRoute allowlist; verified
  the MCP Python SDK's actual env-inheritance behavior (`get_default_environment()` — POSIX:
  HOME/LOGNAME/PATH/SHELL/TERM/USER only, not full `os.environ` — matches the settings.py:439-442
  docstring's claim, just narrower than "default environment" suggests); confirmed the Go
  microservices' `CGO_ENABLED=0` arm64 build is sound (no ARM64 gotcha beyond the orchestrator's
  own prebuilt-image check, which `DEPLOY-RPI5.md` already covers); found the beginner setup
  guide's systemd step references an `openav-mcp/.env` `EnvironmentFile` that step 7 never creates
  (uses `export` instead) — full detail in ARCH.md. Mid-investigation, an exploratory
  `git checkout <branch> -- .` in the sibling `epiphan-openav-bridge` repo accidentally staged one
  file (`.claude/PROJECT_CONTEXT.md`); caught immediately via `git status`, reverted with
  `git restore --staged --worktree`, confirmed clean before continuing. No source files were
  modified in either repo this session.
