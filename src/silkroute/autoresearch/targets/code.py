"""Code Improver target — SilkRoute improving itself.

Evaluates via pytest + coverage + ruff. The agent modifies source files
in src/silkroute/ and the metric is a composite score of test pass rate,
coverage percentage, and lint cleanliness.
"""

from __future__ import annotations

import asyncio
import logging
import re
from pathlib import Path

from silkroute.autoresearch.metrics import Metrics

logger = logging.getLogger(__name__)


class CodeImproverTarget:
    """Research target that optimizes SilkRoute's own code."""

    name = "code"
    allowed_paths = ["src/silkroute/"]
    max_diff_lines = 50

    def __init__(self, project_root: Path) -> None:
        self._root = project_root

    async def evaluate(self) -> Metrics:
        """Run pytest with coverage and ruff, return composite metrics."""
        test_result, coverage_pct = await self._run_pytest()
        lint_clean = await self._run_ruff()

        return Metrics(
            pass_rate=test_result["pass_rate"],
            coverage_pct=coverage_pct,
            lint_clean=lint_clean,
            total_tests=test_result["total"],
            tests_passed=test_result["passed"],
            tests_failed=test_result["failed"],
            error_summary=test_result["error_summary"],
        )

    async def build_context(self, recent_entries: list[dict]) -> str:
        """Build context string with test output, coverage gaps, and history."""
        parts: list[str] = []

        # Current test status
        test_output = await self._get_test_summary()
        parts.append(f"## Current Test Status\n{test_output}")

        # Coverage gaps
        coverage_output = await self._get_coverage_gaps()
        if coverage_output:
            parts.append(f"## Low-Coverage Files\n{coverage_output}")

        # Recent experiment history
        if recent_entries:
            history = "## Recent Experiments\n"
            for entry in recent_entries:
                history += (
                    f"- [{entry['status']}] score={entry['score']:.4f} "
                    f"| {entry['description']}\n"
                )
            parts.append(history)

        return "\n\n".join(parts)

    def get_editable_files(self) -> list[Path]:
        """Return Python files in src/silkroute/ that the agent can edit."""
        src_dir = self._root / "src" / "silkroute"
        files = sorted(src_dir.rglob("*.py"))
        # Exclude autoresearch module itself (no recursive self-improvement)
        return [f for f in files if "autoresearch" not in str(f)]

    async def _run_pytest(self) -> tuple[dict, float]:
        """Run pytest with coverage, return parsed results.

        Uses create_subprocess_exec (no shell) for safety.
        """
        proc = await asyncio.create_subprocess_exec(
            "python", "-m", "pytest",
            "--cov=src", "--cov-report=term-missing",
            "-q", "--tb=line", "--no-header",
            cwd=str(self._root),
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
        )
        stdout, stderr = await asyncio.wait_for(proc.communicate(), timeout=120)
        output = stdout.decode(errors="replace")

        result = {
            "pass_rate": 0.0,
            "total": 0,
            "passed": 0,
            "failed": 0,
            "error_summary": "",
        }
        coverage_pct = 0.0

        # Parse test summary line: "842 passed, 6 failed"
        summary_match = re.search(
            r"(\d+) passed(?:,\s*(\d+) failed)?(?:,\s*(\d+) error)?",
            output,
        )
        if summary_match:
            result["passed"] = int(summary_match.group(1))
            result["failed"] = int(summary_match.group(2) or 0)
            errors = int(summary_match.group(3) or 0)
            result["total"] = result["passed"] + result["failed"] + errors
            if result["total"] > 0:
                result["pass_rate"] = result["passed"] / result["total"]

        # Extract failure lines for context
        fail_lines = [
            line for line in output.splitlines()
            if line.startswith("FAILED") or "ERROR" in line
        ]
        result["error_summary"] = "\n".join(fail_lines[:10])

        # Parse coverage total: "TOTAL    ...    85%"
        cov_match = re.search(r"TOTAL\s+\d+\s+\d+\s+(\d+)%", output)
        if cov_match:
            coverage_pct = int(cov_match.group(1)) / 100.0

        return result, coverage_pct

    async def _run_ruff(self) -> bool:
        """Run ruff check, return True if clean.

        Uses create_subprocess_exec (no shell) for safety.
        """
        proc = await asyncio.create_subprocess_exec(
            "ruff", "check", "src/",
            cwd=str(self._root),
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
        )
        await asyncio.wait_for(proc.communicate(), timeout=30)
        return proc.returncode == 0

    async def _get_test_summary(self) -> str:
        """Get a brief test summary for LLM context."""
        proc = await asyncio.create_subprocess_exec(
            "python", "-m", "pytest",
            "-q", "--tb=line", "--no-header",
            cwd=str(self._root),
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
        )
        stdout, _ = await asyncio.wait_for(proc.communicate(), timeout=120)
        output = stdout.decode(errors="replace")
        # Return last 30 lines (summary + failures)
        lines = output.strip().splitlines()
        return "\n".join(lines[-30:])

    async def _get_coverage_gaps(self) -> str:
        """Get files with coverage below 80% for LLM context."""
        proc = await asyncio.create_subprocess_exec(
            "python", "-m", "pytest",
            "--cov=src", "--cov-report=term-missing",
            "-q", "--no-header", "--tb=no",
            cwd=str(self._root),
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
        )
        stdout, _ = await asyncio.wait_for(proc.communicate(), timeout=120)
        output = stdout.decode(errors="replace")

        # Find lines with coverage < 80%
        low_cov: list[str] = []
        for line in output.splitlines():
            cov_match = re.match(r"(src/\S+)\s+\d+\s+\d+\s+(\d+)%\s*(.*)", line)
            if cov_match and int(cov_match.group(2)) < 80:
                low_cov.append(line.strip())

        return "\n".join(low_cov[:15]) if low_cov else ""
