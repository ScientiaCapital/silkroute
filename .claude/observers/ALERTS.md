# Observer Alerts — silkroute
**Date:** 2026-07-12 (evening close)
**Active BLOCKERs:** 0
**Status:** CLEAR — Local cost dashboard merged to `main` (`a581b0c`), 945/945 tests on merged main, build clean, branch + worktree cleaned up. Backlog #28/#29/#30 resolved; optional follow-ups tracked as #31.

---

## Gate Status for Next Phase

| Check | Result |
|-------|--------|
| Active BLOCKERs | 0 |
| Tests (feature/local-cost-dashboard branch, full suite) | 945/945 PASS |
| Tests (main, prior session) | 928/928 PASS |
| Lint (`ruff check`) | Clean (5 pre-existing errors in cli.py/autoresearch, untouched, unrelated to this session) |
| `npm run build` (dashboard) | Clean |
| E2E verification | Real Postgres + real AV demo run + real API call + real browser render, all confirmed |
| Merge decision for `feature/local-cost-dashboard` | RESOLVED — merged to `main` (`a581b0c`), 945/945 on merged main, branch deleted (2026-07-12 evening) |

_Previous alert (2026-07-12, model registry session) superseded. This is a point-in-time snapshot, not a persistent daemon; re-run at the next `/begin` or phase gate._

---

## 2026-07-21 — Observer Full DA review: branch `feat/edge-mantis-models-openav` (uncommitted)

**Active BLOCKERs:** 2 — DO NOT MERGE until resolved.

### [BLOCKER] `run_agent()`'s inline `SilkRouteSettings()` call breaks 20 tests
- **Found by:** Observer Full
- **Time:** 2026-07-21T20:28:55Z
- **File:** `src/silkroute/agent/loop.py:101`
- **Issue:** `run_agent()` calls bare `SilkRouteSettings()` to read `.hardware_profile` when no
  explicit `hardware_profile` arg is given (true of every current call site, including the CLI).
  `SilkRouteSettings.validate_at_least_one_provider` (`config/settings.py:580`) raises
  `ValidationError` in any environment without a provider key + `ollama_enabled=false` — including
  the test suite. Confirmed via full-suite bisection: base commit 13 failed/1112 passed → diff
  applied 33 failed/1099 passed, a **20-test regression**, all `pydantic_core.ValidationError`,
  spanning `tests/test_loop.py::{TestRunAgent, TestRunAgentStreaming, TestRunAgentWithDB,
  TestFinopsReporting}` and `tests/test_api_demo.py::TestDemoStreamLive`.
- **Required action:** Replace the inline `SilkRouteSettings()` construction with a narrow
  accessor that reads `SILKROUTE_HARDWARE_PROFILE` directly (bypassing the cross-field provider
  validator), matching the pattern every other line in `run_agent` already uses
  (`AgentConfig()`, `BudgetConfig()`, `MemoryConfig()`, `MCPConfig()` — never the top-level
  settings object). Re-run the full suite and confirm it returns to the 13-failure baseline.
- **Status:** OPEN

### [BLOCKER] Hardware-fit routing ignores `ollama_enabled`, now covers STANDARD tier too
- **Found by:** Observer Full
- **Time:** 2026-07-21T20:28:55Z
- **File:** `src/silkroute/agent/router.py:96-97`
- **Issue:** `select_model`'s hardware-fit branch picks a local Ollama model purely from
  `PROFILE_RAM_GB[hardware_profile]` vs. `model.min_ram_gb` — it never checks
  `ProviderConfig.ollama_enabled`. `.env.example`'s unchanged defaults
  (`SILKROUTE_HARDWARE_PROFILE=mac-mini`, `SILKROUTE_OLLAMA_ENABLED=false`) mean a fresh install
  with only an OpenRouter key set will select an Ollama model for FREE/STANDARD work and fail at
  the `litellm.acompletion` call (`loop.py:290-306`, connection refused, no cloud fallback,
  session `FAILED` at iteration 1). Today's diff widens this from FREE-tier-only to also
  STANDARD-tier (`router.py:88-99`), and STANDARD is the tier the AV-control task classifier
  assigns to routine commands.
- **Required action:** Gate the hardware-fit branch on `ollama_enabled` (and ideally a
  reachability check) before returning a local model; add a regression test for
  `hardware_profile` set + `ollama_enabled=False`.
- **Status:** OPEN

_Full findings, contract-drift detail (openav tool allowlist vs. bridge catalog — 12 actual tools
vs. 9 allowlisted, `ec20_jog`/`ec20_preset_save` silently missing), and devil's-advocate
challenges: `.claude/observers/QUALITY.md` and `.claude/observers/ARCH.md`. This is a point-in-time
snapshot; re-run at the next phase gate once the two blockers above are fixed._
