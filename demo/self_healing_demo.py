"""Self-healing AV demo — the control plane heals a room by itself.

Injects a fault into the mock Pearl room, then runs the remediation executor:
read state → detect fault → pick the fix from the playbook → call the MCP action
tool → re-read to VERIFY the room is healthy again. Detect → fix → verify, with
no human in the loop and no LLM required (the playbook is deterministic).

Usage:
    python demo/self_healing_demo.py                       # run all 6 faults
    python demo/self_healing_demo.py --fault signal_loss   # one fault
    python demo/self_healing_demo.py --playbook demo/room_health/some_evolved.yaml

By default it uses the shipped SEED playbook, which handles only 3 of 6 fault
types — so the unhandled faults are visibly "not remediated", which is exactly
the 0.67 score made tangible. Point --playbook at an autoresearch-evolved
playbook for an all-green run.
"""

from __future__ import annotations

import argparse
import asyncio
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent / "src"))

from silkroute.autoresearch.heal import (  # noqa: E402 — sys.path shim above
    DEFAULT_PLAYBOOK_PATH,
    HealResult,
    heal_with_mock,
)

FAULTS = [
    "recorder_stopped",
    "signal_loss",
    "storage_full",
    "storage_unmounted",
    "device_offline",
    "cpu_overload",
]

_ICON = {"healed": "✅", "unhandled": "⚠️ ", "healthy": "💤"}


def _print_result(fault: str, r: HealResult) -> None:
    print(f"\n── Fault injected: {fault} ──")
    for step in r.steps:
        print(f"   • {step}")
    verdict = {
        "healed": f"{_ICON['healed']} HEALED via {r.action}()",
        "unhandled": f"{_ICON['unhandled']}UNHANDLED — no playbook fix (evolve via autoresearch)",
        "healthy": f"{_ICON['healthy']} already healthy",
    }[r.outcome]
    print(f"   → {verdict}")


async def _run(faults: list[str], playbook: Path) -> int:
    print(f"Self-Healing AV Demo\n  Playbook: {playbook}\n  Faults: {', '.join(faults)}")
    healed = 0
    for fault in faults:
        result = await heal_with_mock(fault, playbook_path=playbook)
        _print_result(fault, result)
        healed += result.outcome == "healed"
    print(f"\n{'=' * 60}\nHealed {healed}/{len(faults)} rooms autonomously.")
    if healed < len(faults):
        print("Unhealed faults are unhandled by this playbook — run")
        print("  silkroute research start -t room-health -m deepseek/deepseek-v3.2")
        print("to evolve the playbook, then re-run this demo.")
    print("=" * 60)
    return 0


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--fault", choices=FAULTS, help="Inject one fault (default: all)")
    parser.add_argument(
        "--playbook",
        default=str(DEFAULT_PLAYBOOK_PATH),
        help="Path to the remediation playbook (default: the shipped seed)",
    )
    args = parser.parse_args()
    faults = [args.fault] if args.fault else FAULTS
    asyncio.run(_run(faults, Path(args.playbook)))


if __name__ == "__main__":
    main()
