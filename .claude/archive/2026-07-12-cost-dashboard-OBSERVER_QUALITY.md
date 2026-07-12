# Code Quality Audit — silkroute

**Date:** 2026-07-12  
**Scope:** Recent commits (HEAD~5..HEAD) — MCP bridge, finops telemetry, model registry expansion, direct-vendor routing  
**Auditor:** Observer Lite (point-in-time scan)

---

## Findings

### [WARNING] — src/silkroute/agent/loop.py:455,465 — Silent exception handlers in _extract_cost()

**Issue:** Two bare `except Exception: pass` blocks swallow errors without logging:
- Line 455: Fallback 1 (litellm.completion_cost)
- Line 465: Fallback 2 (_hidden_params extraction)

**Context:** Intentional design — the function has a triple-fallback cost extraction strategy (litellm → hidden_params → estimate_cost). Exceptions are expected and caught, but lack logging makes debugging harder.

**Suggested fix:** Add `log.debug()` or `log.warning()` before the `pass` to surface why each fallback triggered. This is already tracked in backlog item #21.

```python
except Exception as e:
    log.debug("cost_extraction_fallback_1_failed", error=str(e))
```

---

## Code Quality Summary

| Category | Result | Notes |
|----------|--------|-------|
| **Secrets scan** | ✅ PASS | No hardcoded API keys, tokens, or credentials. All sensitive values loaded via Pydantic BaseSettings from env vars. |
| **Test coverage** | ✅ PASS | Comprehensive test files exist: test_finops_client.py (4 test classes), test_mcp_bridge.py (4 test cases), test_model_registry.py (6 integrity tests), test_router.py (model routing), test_models.py (model specs). |
| **Silent failures** | ⚠️  WARNING | 2 bare `except Exception: pass` blocks in loop.py (see above). No other bare except blocks detected. |
| **Tech debt markers** | ✅ PASS | 0 TODO/FIXME/HACK/XXX comments found across src/ |
| **Unused imports** | ✅ PASS | Ruff F401 check passed; no unused imports. |
| **Hardcoded values** | ✅ PASS | Only legitimate API endpoint URLs (api.deepseek.com, dashscope.aliyuncs.com, open.bigmodel.cn, openrouter.ai). No magic numbers or suspicious string literals. |

---

## Monitoring Runs

| Category | Status | Details |
|----------|--------|---------|
| **Secrets detection** | ✅ CLEAN | Grep patterns (sk_, ghp_, AKIA, private_key, client_secret) returned no matches in source. .env files properly gitignored. |
| **Lint (ruff)** | ✅ CLEAN | All recently changed files pass. Zero F401 (unused imports), zero F841 (unused variables). |
| **Exception patterns** | ⚠️  1 ISSUE | 2 silent fallback handlers in _extract_cost() flagged. All other exception blocks properly logged or re-raised. |
| **Test files** | ✅ EXIST | All changed modules have corresponding test files with good coverage. |
| **Architecture** | ✅ SOUND | Fail-open design pattern consistent: finops reporting, MCP bridge connection, all have proper error swallowing with non-fatal fallbacks. |

---

## Summary

The recent commits (MCP bridge, finops telemetry, model registry expansion) introduce clean, well-tested code. One minor code quality issue: two silent exception fallbacks in `_extract_cost()` lack debug logging, making it harder to understand why fallbacks triggered. This is a known backlog item (#21). No blockers; no secrets; no test gaps; no debt markers.

**Status:** ✅ PASS (1 known issue, non-blocking)
