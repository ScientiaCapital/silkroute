"""Shared room-health remediation playbook engine.

The single source of truth for loading a remediation playbook and deciding which
remediation action a room's fault signature calls for. Used by BOTH:

- ``RoomHealthTarget`` (autoresearch) — to *score* a playbook against fixtures.
- ``heal.py`` (runtime executor) — to *act*: pick the remediation to apply.

Keeping one engine guarantees the executor heals a room using exactly the logic
the autoresearch loop optimized.

Playbook shape (YAML): a mapping with a ``rules`` list. Each rule is
``{id, when: {signal: condition, ...}, action}``. Rules are checked top-to-bottom
and the FIRST rule whose ``when`` conditions ALL match decides the action; if
none match, the action is ``none``.

Signals: device_state, recorder_state, input_has_signal, storage_mounted,
storage_percent_used, cpu_percent.

Condition forms: ``value`` (equals) · ``{ne: value}`` · ``{gte: N}`` / ``{gt: N}``
/ ``{lte: N}`` / ``{lt: N}`` / ``{eq: value}``.
"""

from __future__ import annotations

import operator
from pathlib import Path
from typing import Any

import yaml

# Remediation actions a playbook may prescribe. `none` = no action needed.
KNOWN_ACTIONS = frozenset(
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


def load_playbook(path: Path) -> tuple[list[dict[str, Any]], bool, str]:
    """Load and validate a playbook file.

    Returns ``(usable_rules, lint_clean, error)``. Malformed rules are skipped
    (so a partially-broken file still evaluates), but any structural problem or
    unknown action flips ``lint_clean`` False.
    """
    try:
        raw = yaml.safe_load(path.read_text())
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
            or rule.get("action") not in KNOWN_ACTIONS
        ):
            lint_clean = False
            continue
        if rule.get("id") in seen_ids:
            lint_clean = False
        seen_ids.add(rule.get("id"))
        rules.append(rule)
    return rules, lint_clean, ""


def decide_action(rules: list[dict[str, Any]], signals: dict[str, Any]) -> str:
    """First rule whose conditions all match wins; else 'none'."""
    for rule in rules:
        if _rule_matches(rule["when"], signals):
            return str(rule["action"])
    return "none"


def _rule_matches(when: dict[str, Any], signals: dict[str, Any]) -> bool:
    return all(
        key in signals and _condition_holds(cond, signals[key])
        for key, cond in when.items()
    )


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
