# SilkRoute: Architecture Observer Report

**Date:** 2026-07-21T20:28:55Z
**Session:** Observer Full — DA review of edge/openav plan
**Scope:** silkroute `feat/edge-mantis-models-openav` (uncommitted, 10 files vs `main`) driving a real
Epiphan Pearl Mini + EC20 via `epiphan-openav-bridge` `feat/ec20-hybrid-driver`, targeting a
Raspberry Pi 5 (cloud-delegated) or an Ubuntu box (local Ollama for FREE/STANDARD).
**Status:** BLOCKERS FOUND (2, cross-referenced with QUALITY.md — see there for the full-suite
bisection proving a 20-test regression from the `SilkRouteSettings()`/router changes)

---

## Contract Compliance

No formal `.claude/contracts/` file exists for this branch — **[WARNING]: no feature contract
defined**. Reviewed against the team-lead's stated design intent (Haiku 4.5 ModelSpec,
hardware_profile wiring, openav MCP preset) instead.

| Area | Compliant? | Notes |
|---|---|---|
| Haiku 4.5 ModelSpec (`providers/models.py:416-435`) | Yes | STANDARD tier, OpenRouter route, registry 21→22, tests updated to match |
| `hardware_profile` → `select_model()` wiring (`loop.py:93-103`) | **No — see BLOCKER, QUALITY.md** | Breaks 20 existing tests (confirmed via full-suite bisection, not just the 3 finops ones originally suspected); couples `run_agent` to full-settings validation |
| `openav_*` MCPConfig preset (`settings.py:341-466`) | Partial | Preset/read-only/env-merge mechanics are correct and well-tested (`tests/test_mcp_config.py`); the **tool allowlist content** drifts from the actual bridge catalog (below) |
| `.env.example` / `docs/edge-deployment.md` | Mostly | Correct in isolation, but silently inherits the router bug above (mac-mini + ollama disabled is the literal default) |

## Findings

[BLOCKER] — **Contract drift: openav tool allowlist vs actual bridge catalog.**
`src/silkroute/config/settings.py:387-406` (`openav_tool_allowlist` + its doc comment) claims the
bridge exposes "only 10 tools" with `ec20_tracking` as the sole intentional exclusion. Ground
truth, `epiphan-openav-bridge/openav-mcp/openav_mcp/server.py:39-89` (`_SPECS`), is **12 tools**:
`set_room_state, run_scene, list_room_controls, pearl_control_recording, pearl_singletouch,
pearl_status, ec20_jog, ec20_preset_recall, ec20_preset_save, ec20_tracking, ec20_ptz,
ec20_status`. SilkRoute's allowlist has 9 — `ec20_jog` and `ec20_preset_save` are dropped in
addition to `ec20_tracking`, with no mention in the comment or in
`docs/edge-deployment.md`'s "Security posture" section (which also only names `ec20_tracking` as
excluded). Consequences:
  - `ec20_jog` is the bridge's own documented **preferred** live-framing verb ("Preferred for
    live framing", server.py:62) — a relative VISCA nudge. The allowlist instead exposes only
    `ec20_ptz`, which the bridge's own comment calls "secondary" and "calibrated best-effort"
    (absolute pan/tilt/zoom degrees, server.py:60-61, 79). The agent gets the worse tool for the
    documented-common case and lacks the better one.
  - `ec20_preset_save` (save current position to a preset slot) is entirely unavailable — a user
    asking the agent to "save this framing as preset 3" has no path to succeed, silently.
  - This is exact-match contract drift (field/name-level), not a schema-shape issue, so it's easy
    to miss in review — the fix is a one-line allowlist edit (add `ec20_jog`, `ec20_preset_save`)
    plus correcting the "10 tools" comment to 12, in both `settings.py` and
    `docs/edge-deployment.md`.

[WARNING] — **Beginner guide gap: systemd `EnvironmentFile` never created.**
`epiphan-openav-bridge/demo/DEPLOY-RPI5.md` step 8 (autostart) ships a systemd unit with
`EnvironmentFile=/home/<user>/epiphan-openav-bridge/openav-mcp/.env` — but step 7 (the only prior
place `openav-mcp` env vars are set) uses seven `export VAR=...` shell commands, never writing a
`.env` file. `systemd`'s `EnvironmentFile=` (no leading `-`) causes the unit to fail to start if
the referenced file is absent. A beginner following the guide verbatim through "8. Autostart on
boot" for the "only if it must run resident" branch will hit `systemctl enable --now
openav-mcp` failing outright. This is the exact gap the team-lead's review predicted. **Fix:**
either (a) have step 7 write the exports to `openav-mcp/.env` (`cat > .env <<EOF ... EOF`) and
`set -a; source .env; set +a` before the manual `python -m openav_mcp` smoke test, so the same
file backs both the interactive test and the systemd unit, or (b) note that the systemd path is
for the "SilkRoute is not spawning it" case only and cross-reference a `.env` template. Note: this
branch of the guide (`openav-mcp` run resident, not agent-spawned) is explicitly the fallback
path — the primary, recommended path (SilkRoute spawns `openav-mcp` itself as a stdio subprocess,
guide step 7's callout box) does **not** hit this bug, since SilkRoute's own `MCPConfig.openav_*`
settings supply the env directly with no file involved. Severity kept at WARNING rather than
BLOCKER because the primary documented path is unaffected; still real for anyone using the
resident/systemd option.

[WARNING] — **Scope creep, mild:** the branch's actual diff (10 files, +252/-18) is narrower and
cleaner than what the team-lead's message described as "changed today" (Haiku 4.5, hardware_profile
wiring, openav MCP preset, docs, dashboard mirror) — all present, nothing extra. No scope-creep
found in-repo. The scope-creep risk instead lives at the **system** level: the plan couples three
independently-versioned repos (silkroute, epiphan-openav-bridge, Dartmouth OpenAV upstream image) with
no integration test that spans the seam — each repo's test suite is green-ish in isolation (silkroute:
13 pre-existing + 20 new-regression failures, both accounted for in QUALITY.md; bridge: not re-run
this session, team-lead's message states 74/13 tests passing) but nothing exercises "SilkRoute
spawns real openav-mcp, which calls real (or mocked) Go microservices" end-to-end. Recommend a
smoke test using `OPENAV_MOCK=true` (already supported per `openav_mcp/config.py:43,93`) wired into
SilkRoute's own test suite via `connect_mcp_server` against a locally-spawned openav-mcp — this
would have caught the tool-allowlist drift above automatically.

[INFO] — **Cross-repo env-inheritance is safe by construction, but the docstring overclaims.**
`config/settings.py:439-442` and `mcp_bridge/client.py:35-38` both describe the subprocess env as
"merged on top of the subprocess's default environment, not replacing it — PATH/HOME etc. are
preserved." True, but "default environment" (`mcp.client.stdio.get_default_environment()`) is a
locked-down allowlist (POSIX: `HOME, LOGNAME, PATH, SHELL, TERM, USER` — nothing else), not the
parent's full `os.environ`. In practice this is fine here because `openav_mcp/config.py` reads
*only* the four `OPENAV_*` vars SilkRoute explicitly forwards (verified: no other env reads, no
relative-path `.env`/dotenv loading, no CWD dependency — `StdioServerParameters.cwd` is also never
set by SilkRoute, defaulting to inherit the parent's cwd, which doesn't matter here for the same
reason). Flagging only so the docstring's "default environment" phrasing isn't later mistaken for
"full environment" when a future integration needs a var not in that six-item allowlist (e.g. a
proxy var, a locale, an API key some other MCP server DOES want inherited).

## Devil's Advocate Challenges

| Target | Challenge | Verdict |
|---|---|---|
| `SilkRouteSettings()` inline construction in `loop.py:101` | Does it need to exist at all? A single-field read shouldn't require validating every provider key, MCP preset, budget config, etc. | **Upheld — real bug, confirmed to break 20 tests via full-suite bisection.** Simpler fix: read the env var directly. |
| `CLAUDE_HAIKU_4_5` ModelSpec (`providers/models.py:416-435`) | Is a 6th western model necessary, or could the existing `GEMINI_3_5_FLASH`/`GPT_5_6_LUNA` STANDARD-tier entries cover "fast, cheap, tool-calling"? | Not upheld — the doc comment gives a real, specific rationale (latency-first for live-event control, distinct from the two existing STANDARD-tier western entries which aren't framed for latency), and it's a one-line, low-maintenance addition consistent with the model-agnostic OpenRouter pattern. No objection. |
| `openav_tool_allowlist` as a hardcoded list vs. deriving from the bridge's `list_tools()` at connect time minus a denylist | Simpler to maintain a `deny` set (just `ec20_tracking`) than an `allow` set that must be kept in sync with a catalog in a *different repo* | **Upheld as a design concern**, independent of the miscount bug above — an allowlist that must track another repo's growing tool catalog by hand is exactly how this drift happened, and will happen again the next time the bridge adds a tool. A denylist (or a generated/tested allowlist, per the scope-creep smoke-test suggestion) would be structurally safer. |
| `--read-only` gating implemented on both sides (SilkRoute's allowlist AND openav-mcp's own `mutating_enabled` check in `_call`, server.py:134-145) | Is the double-gating redundant, or is it defense-in-depth? | Not upheld as a problem — belt-and-suspenders is correct here: SilkRoute's allowlist controls what the LLM even *sees*, openav-mcp's own check controls what it will *execute* even if called directly (e.g. a future non-SilkRoute MCP client). No change recommended. |
| Two-repo, three-language deployment (Python orchestrator + Go microservices + Python MCP layer) on a Pi 5 | Could this be one process/one repo instead? | Out of scope for this diff (pre-existing architecture, not introduced today) — noting only that it's the reason the `OPENAV_MOCK` smoke-test gap above exists: there's no cheap way to test the full seam without standing up (or mocking) three separate services. |

## Not Reviewed / Out of Scope This Pass

- Latency/live-event worst-case timing: qualitatively, each `silkroute run` command is a cold
  start (fresh `run_agent()` session, fresh `openav-mcp` stdio subprocess spawn + `list_tools()`
  round-trip, no connection reuse across commands) plus 1+ cloud LLM round-trip. The team's own
  prior empirical finding (documented 2026-07-18, live-agent-mode work) showed a local qwen2.5:14b
  sometimes fails to converge within a small `max_iterations` (18-56s observed, non-convergent in
  one run) — the same non-convergence risk applies here with `run_agent`'s default
  `max_iterations=25` (the CLI's own default, `cli.py:73`), uncapped further by anything but the
  $10 default budget check. Did not reproduce live against real hardware this session (no
  device/cloud-key access) — flagging as a RISK worth a real timed test before a live event, not a
  confirmed BLOCKER.
- Full bridge-repo test suite re-run (deferred to the bridge repo's own CI/observer).

## Session Notes

Mid-investigation, an exploratory `git checkout feat/ec20-hybrid-driver -- .` in the sibling
`epiphan-openav-bridge` repo (intended only to list files on that branch without switching HEAD)
accidentally staged one file (`.claude/PROJECT_CONTEXT.md`) into that repo's working tree. Caught
immediately via `git status --porcelain=v1 -uno`, reverted with
`git restore --staged --worktree .claude/PROJECT_CONTEXT.md`, confirmed clean before continuing.
No source files were modified in either repo this session; all subsequent cross-repo reads used
`git show <ref>:<path>` / `git ls-tree` instead.
