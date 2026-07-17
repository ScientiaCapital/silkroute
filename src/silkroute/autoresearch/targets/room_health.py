"""Room-health target — a self-healing AV control plane, evolved by autoresearch.

The second ResearchTarget (proves the protocol generalizes beyond code, #26).
Instead of editing source files, the agent iterates on a *remediation playbook*
(`demo/room_health/remediation_rules.yaml`): declarative rules that map a room's
fault signature → the remediation action that fixes it. The engine scores the
playbook against a held-out fault-scenario set (`demo/room_health/
fault_scenarios.json`) and keeps changes that remediate more faults — the same
modify → eval → keep/discard loop the code target uses, so NO engine changes.

Why a playbook file rather than live device calls: the engine's unit of work is
a file edit + git commit/reset. Making the rules the editable artifact lets a
"detect fault → choose fix → verify" task fit that machinery cleanly and run
deterministically (the eval is offline against fixtures, no live Pearl needed).

Metrics mapping (reuses the code-quality Metrics fields — the engine only reads
.score/.pass_rate/.coverage_pct/.is_better_than/.summary):
    pass_rate    = fault scenarios correctly remediated / total
    coverage_pct = distinct fault types covered / total fault types
    lint_clean   = the playbook is valid (parses, known actions, well-formed)
"""

from __future__ import annotations

import json
import logging
import operator
from pathlib import Path
from typing import Any

import asyncpg
import yaml

from silkroute.autoresearch.metrics import Metrics
from silkroute.config.settings import MemoryConfig

logger = logging.getLogger(__name__)

# Remediation actions the playbook may prescribe. `none` = no action needed.
_KNOWN_ACTIONS = frozenset(
    {
        "start_recorder",
        "restart_input",
        "rotate_recordings",
        "remount_storage",
        "reboot_device",
        "throttle_channels",
        "none",
    }
)

# Comparison operators the `when` DSL supports, as safe callables (no eval).
_COMPARATORS = {
    "eq": operator.eq,
    "ne": operator.ne,
    "gt": operator.gt,
    "lt": operator.lt,
    "gte": operator.ge,
    "lte": operator.le,
}


class RoomHealthTarget:
    """Research target that evolves a self-healing AV remediation playbook."""

    name = "room-health"
    # Scope edits to the playbook ONLY — the agent must not touch the scenario
    # fixtures (that would be editing the test to pass it).
    allowed_paths = ["demo/room_health/remediation_rules.yaml"]
    max_diff_lines = 40

    def __init__(self, project_root: Path, project_id: str = "default") -> None:
        self._root = project_root
        self._project_id = project_id
        self._rules_path = project_root / "demo" / "room_health" / "remediation_rules.yaml"
        self._scenarios_path = project_root / "demo" / "room_health" / "fault_scenarios.json"
        # Per-scenario outcome of the most recent evaluate(), reused by
        # build_context() so it doesn't re-run the eval.
        self._last_report: list[dict[str, Any]] | None = None

    # --- ResearchTarget protocol ---

    async def evaluate(self) -> Metrics:
        """Score the current playbook against every fault scenario."""
        rules, lint_clean, _lint_error = self._load_rules()
        scenarios = self._load_scenarios()

        report: list[dict[str, Any]] = []
        for scenario in scenarios:
            chosen = self._decide_action(rules, scenario["signals"])
            expected = scenario["expected_action"]
            report.append(
                {
                    "id": scenario["id"],
                    "fault_type": scenario["fault_type"],
                    "expected": expected,
                    "chosen": chosen,
                    "ok": chosen == expected,
                }
            )
        self._last_report = report

        total = len(report)
        passed = sum(1 for r in report if r["ok"])
        failed = total - passed
        pass_rate = passed / total if total else 0.0

        fault_types = {r["fault_type"] for r in report}
        covered = {r["fault_type"] for r in report if r["ok"]}
        coverage_pct = len(covered) / len(fault_types) if fault_types else 0.0

        error_summary = "\n".join(
            f"{r['id']} ({r['fault_type']}): expected {r['expected']}, got {r['chosen']}"
            for r in report
            if not r["ok"]
        )

        return Metrics(
            pass_rate=pass_rate,
            coverage_pct=coverage_pct,
            lint_clean=lint_clean,
            total_tests=total,
            tests_passed=passed,
            tests_failed=failed,
            error_summary=error_summary,
        )

    async def build_context(self, recent_entries: list[dict]) -> str:
        """Build the LLM context: current status, unhandled faults, history."""
        if self._last_report is None:
            await self.evaluate()
        report = self._last_report or []

        parts: list[str] = []

        passed = sum(1 for r in report if r["ok"])
        parts.append(
            f"## Current Remediation Status\n"
            f"{passed}/{len(report)} fault scenarios correctly remediated."
        )

        unhandled = [r for r in report if not r["ok"]]
        if unhandled:
            lines = "\n".join(
                f"- {r['id']} — fault '{r['fault_type']}': "
                f"the playbook chose '{r['chosen']}', but '{r['expected']}' resolves it"
                for r in unhandled
            )
            parts.append(f"## Faults NOT yet remediated\n{lines}")

        if recent_entries:
            history = "## Recent Experiments\n"
            for entry in recent_entries:
                history += (
                    f"- [{entry['status']}] score={entry['score']:.4f} "
                    f"| {entry['description']}\n"
                )
            parts.append(history)

        memory_section = await self._build_memory_section()
        if memory_section:
            parts.append(memory_section)

        return "\n\n".join(parts)

    def get_editable_files(self) -> list[Path]:
        """The playbook is the only file the agent edits."""
        return [self._rules_path]

    def invalidate_eval_cache(self) -> None:
        """Drop the cached per-scenario report (e.g. after a git reset)."""
        self._last_report = None

    # --- rule engine ---

    def _load_rules(self) -> tuple[list[dict[str, Any]], bool, str]:
        """Load and validate the playbook.

        Returns (usable_rules, lint_clean, error). Malformed rules are skipped
        (so a partially-broken file still evaluates), but any structural problem
        or unknown action flips lint_clean False.
        """
        try:
            raw = yaml.safe_load(self._rules_path.read_text())
        except (OSError, yaml.YAMLError) as exc:
            return [], False, f"playbook did not parse: {exc}"

        if not isinstance(raw, dict) or not isinstance(raw.get("rules"), list):
            return [], False, "playbook must be a mapping with a 'rules' list"

        rules: list[dict[str, Any]] = []
        lint_clean = True
        seen_ids: set[str] = set()
        for rule in raw["rules"]:
            if (
                not isinstance(rule, dict)
                or not isinstance(rule.get("when"), dict)
                or rule.get("action") not in _KNOWN_ACTIONS
            ):
                lint_clean = False
                continue
            if rule.get("id") in seen_ids:
                lint_clean = False
            seen_ids.add(rule.get("id"))
            rules.append(rule)
        return rules, lint_clean, ""

    def _load_scenarios(self) -> list[dict[str, Any]]:
        data = json.loads(self._scenarios_path.read_text())
        return list(data["scenarios"])

    def _decide_action(self, rules: list[dict[str, Any]], signals: dict[str, Any]) -> str:
        """First rule whose conditions all match wins; else 'none'."""
        for rule in rules:
            if self._rule_matches(rule["when"], signals):
                return str(rule["action"])
        return "none"

    def _rule_matches(self, when: dict[str, Any], signals: dict[str, Any]) -> bool:
        return all(
            key in signals and self._condition_holds(cond, signals[key])
            for key, cond in when.items()
        )

    @staticmethod
    def _condition_holds(cond: object, value: object) -> bool:
        """Evaluate one condition against a signal value (no eval, safe)."""
        if isinstance(cond, dict):
            for op, operand in cond.items():
                fn = _COMPARATORS.get(op)
                if fn is None:
                    return False
                try:
                    if not fn(value, operand):
                        return False
                except TypeError:
                    return False
            return True
        # Scalar condition → exact equality (bool compared strictly vs int).
        return type(value) is type(cond) and value == cond

    # --- memory (fail-open, mirrors CodeImproverTarget) ---

    async def _build_memory_section(self) -> str:
        """Recall recent agent_memories outcomes. Fail-open — never raises."""
        if not MemoryConfig().enabled:
            return ""
        try:
            from silkroute.db.pool import get_pool

            pool = await get_pool()
        except (ImportError, asyncpg.PostgresError, OSError, TimeoutError) as exc:
            logger.warning("room_health_memory_pool_unavailable: %s", exc)
            return ""
        if pool is None:
            return ""
        try:
            from silkroute.db.repositories.memories import recall_memories

            memories = await recall_memories(pool, self._project_id, limit=5)
        except Exception as exc:  # noqa: BLE001 — memory is best-effort context
            logger.warning("room_health_memory_recall_failed: %s", exc)
            return ""
        if not memories:
            return ""
        lines = "\n".join(f"- [{m['kind']}] {m['content']}" for m in memories)
        return f"## Relevant Past Learnings\n{lines}"
