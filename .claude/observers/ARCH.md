# SilkRoute: Architecture Observer Report
**Date:** 2026-07-12
**Session:** Start-of-day `/begin` audit (Phase 2) — reviewing commits 36a3ac3, 4d5dde2 (MCP bridge, model-finops telemetry, expanded local model registry) against `71c1f13`, `8a47ddf`, `220f137`
**Status:** CLEAR — 0 BLOCKERs, 3 WARNINGs, 2 SMELLs

---

## Scope Reviewed

`git diff --stat HEAD~5..HEAD` — 31 files, +1520/-99. New: `src/silkroute/mcp_bridge/` (client.py, __init__.py), `src/silkroute/integrations/finops_client.py`, `demo/pearl_mock_server.py`, `demo/agent_ready_av_demo.py`, `docs/av-demo-guide.md`, `tests/fixtures/fake_mcp_server.py`, plus 4 new test files. Modified: `agent/loop.py`, `agent/router.py`, `config/settings.py`, `providers/models.py`, `providers/openrouter.py`, `pyproject.toml`, `CLAUDE.md`, `.claude/rules/coding.md`.

## Contract Compliance

| Convention (CLAUDE.md / coding.md) | Status | Note |
|---|---|---|
| No OpenAI — Chinese LLMs only | PASS | No `openai` references in any changed file. New Ollama entries (Qwen/DeepSeek/GLM) and MCP bridge are provider-agnostic transport, not a new model vendor. |
| Direct vendor APIs when keys configured, OpenRouter fallback | PASS | `router.py` cascade correctly prefers direct transport (`_is_provider_available`) then falls back to `openrouter/` prefix. `CLAUDE.md`/`coding.md` wording for this was already updated in a prior commit (`71c1f13`), consistent with current code. |
| 3-tier routing (Free/Standard/Premium) | PASS | New local models all correctly slotted into `ModelTier.FREE`; tier structure untouched. |
| Budget governance | PASS | Not touched this session; `loop.py` budget checks unchanged. |
| No feature contract in `.claude/contracts/` for this work | **WARNING** | No contract file for "MCP bridge" or "finops telemetry" exists in `.claude/contracts/` (11 phase contracts exist, none for this session's scope). Repo convention has drifted toward PROJECT_CONTEXT.md-based session logs instead of formal contracts — noted in Backlog/PROJECT_CONTEXT as intentional, but no explicit acceptance decision found for skipping contracts on FULL-scope work of this size (+1520 lines, 3 new subsystems). |

## Findings

**[WARNING] — `src/silkroute/providers/models.py:386-422` — Two Ollama model tags shipped with self-flagged UNVERIFIED status — could waste a Railway/local demo session if wrong**
`DEEPSEEK_R1_14B_LOCAL` (`ollama/deepseek-r1:14b`) and `GLM_CURRENT_LOCAL` (`ollama/glm4.6:9b`) were added with no internet access to confirm the tags exist in the Ollama library. **Devil's-advocate check on actual blast radius: this is well-contained, not a real runtime risk.**
- Neither tag appears in `DEFAULT_ROUTING` (`models.py:479-499`), and `select_model()`'s Level 2/3 cascade explicitly filters `provider != Provider.OLLAMA` (`router.py:51`, `router.py:60`) — so automatic tier-based routing can **never** select either model.
- The only way to reach them is an explicit `--model ollama/deepseek-r1:14b` (or `glm4.6:9b`) override — Level 1 of the cascade (`router.py:40-43`).
- If invoked, `litellm.acompletion()` is wrapped in `try/except Exception` in `loop.py:267-284` — a bad tag fails loudly (session marked `FAILED`, error logged and printed), it does **not** silently fall back to a different/wrong model.
- Already self-documented in code comments (`models.py:382-385`, `403-406`) and tracked in `Backlog.md:100` and `PROJECT_CONTEXT.md:23` ("Tomorrow" section) as a verify-before-pull action item.
- **Verdict: SMELL, not RISK/BLOCKER.** Downgrading from what the assignment brief flagged as a potential concern — the fail-loud + opt-in-only design makes this safe to leave for tomorrow's verification step as already planned.

**[WARNING] — `src/silkroute/providers/openrouter.py` — 130 lines changed/added but not mentioned in PROJECT_CONTEXT.md's "Done" list**
Backlog/PROJECT_CONTEXT attribute this session's changes to `mcp_bridge`, `finops_client`, and `models.py`, but `git diff --stat` shows `providers/openrouter.py` had the second-largest diff of any file (+/-130 lines) after `models.py`. `tests/test_openrouter.py` also grew by 54 lines. This is very likely support code for the `DIRECT_MODEL_NAMES` translation table (native vendor model-name mapping) from the *prior* commit `71c1f13`, not new scope creep from today's session — but PROJECT_CONTEXT.md's "Tomorrow" section assumes tomorrow's verification work is only about Ollama tags and telemetry, when `DIRECT_MODEL_NAMES` (`models.py:516-530`, also unverified per its own header comment) is an equally-unverified surface that isn't called out in tomorrow's plan.
- **Gap between "Tomorrow" and reality**: `Backlog.md:99` does list "Verify DIRECT_MODEL_NAMES... against vendor docs" — so this is actually tracked, just not mirrored into PROJECT_CONTEXT.md's shorter "Tomorrow" line. Not a blocker, just a documentation-sync nit between the two files.

**[SMELL] — `demo/` — new top-level directory not reflected in CLAUDE.md's architecture tree**
`CLAUDE.md`'s repo layout diagram (lines 8-16) lists `src/silkroute/`, `dashboard/`, `sql/`, `docker-compose.yml`, `litellm_config.yaml`, `pyproject.toml`, `tests/` but not `demo/` or `docs/`, both newly populated this session. Low impact (demo/docs are additive, not contract-violating), but the canonical architecture diagram is now stale.

**[SMELL] — `src/silkroute/mcp_bridge/client.py:73` — broad `except Exception` on the whole connect+register flow**
`connect_mcp_server()` wraps subprocess spawn, session init, `list_tools()`, and tool registration in one broad `except Exception`, logging and returning `None`. This matches the file's own documented contract ("Returns None if the connection failed... callers should treat that as non-fatal") and the repo's established fire-and-forget/fail-open pattern (`finops_client.py`, `context7.py`), so this is intentional and consistent — not the same class of finding as the narrowed-exception hardening done in Phase 7. No action needed; noting only because pattern-1 scanning surfaces all broad excepts by design.

## Devil's Advocate Challenges

| File | Challenge | Verdict |
|---|---|---|
| `src/silkroute/mcp_bridge/client.py` | Does a whole new generic MCP client module need to exist, or could this reuse `ToolRegistry`'s existing tool-loading path? | Justified — no existing code in this repo speaks the MCP stdio protocol; this is a genuinely new integration surface (first MCP client in the repo, per its own docstring), not a duplicate of anything in `agent/tools.py`. |
| `src/silkroute/integrations/finops_client.py` | Is a whole new `integrations/` package warranted for one function (`report_usage`)? | Reasonable — mirrors the existing `mantis/skills/context7.py` fire-and-forget HTTP client pattern already established in this repo; a new top-level package for "external service integrations" is a sane home if more are added later, though today it holds exactly one file. Low cost either way. |
| `providers/models.py` — 6 new Ollama entries in one commit | Could the 2 unverified tags have waited for verification before being committed to the registry at all? | Fair challenge — shipping unverified data into a registry that's read by production routing code (even if unreachable via automatic cascade, per finding above) is slightly riskier than keeping them in a scratch/draft state until confirmed. Mitigated by clear UNVERIFIED naming/comments and cascade exclusion, but the cleaner sequencing would have been: verify first, then add. Not worth reverting now given the safety net in place. |
| `demo/pearl_mock_server.py` — new stdlib `http.server`-based mock | Could an existing test fixture (`tests/fixtures/fake_mcp_server.py`) have been reused instead of a second bespoke mock server? | Not a duplicate — `fake_mcp_server.py` mocks the MCP protocol layer (tool discovery/calling) for `test_mcp_bridge.py`, while `pearl_mock_server.py` mocks the downstream Pearl device HTTP API that epiphan-mcp-server itself calls. Different layers, legitimately separate. |

## No Contract Drift to Report
No feature contract exists for this session's scope (MCP bridge / finops / model registry expansion), so pattern 7 (Contract Drift — response shapes, field names) has nothing to check against. See Contract Compliance table above.

---
_Previous report (2026-03-22, Phase 10) superseded. Session: `/begin` Phase 2 architecture audit, 2026-07-12._
