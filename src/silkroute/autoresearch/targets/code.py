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

import asyncpg

from silkroute.autoresearch.metrics import Metrics
from silkroute.config.settings import MemoryConfig

logger = logging.getLogger(__name__)


class CodeImproverTarget:
    """Research target that optimizes SilkRoute's own code."""

    name = "code"
    allowed_paths = ["src/silkroute/"]
    max_diff_lines = 50

    def __init__(self, project_root: Path, project_id: str = "default") -> None:
        self._root = project_root
        self._project_id = project_id
        # Raw output of the most recent pytest --cov run. evaluate() refreshes
        # it; build_context()'s helpers parse from it instead of re-running the
        # suite (backlog #24 — pytest used to run up to 3x per experiment).
        self._last_eval_output: str | None = None

    async def evaluate(self) -> Metrics:
        """Run pytest with coverage and ruff, return composite metrics."""
        output = await self._run_pytest_subprocess()
        self._last_eval_output = output
        test_result, coverage_pct = self._parse_pytest_output(output)
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

        # Past learnings from persistent memory (this project + global)
        memory_section = await self._build_memory_section()
        if memory_section:
            parts.append(memory_section)

        return "\n\n".join(parts)

    async def _build_memory_section(self) -> str:
        """Recall recent agent_memories outcomes. Fail-open — never raises."""
        if not MemoryConfig().enabled:
            return ""
        try:
            from silkroute.db.pool import get_pool

            pool = await get_pool()
        except (ImportError, asyncpg.PostgresError, OSError, TimeoutError) as exc:
            logger.warning("code_target_memory_pool_unavailable: %s", exc)
            return ""
        if pool is None:
            return ""
        try:
            from silkroute.db.repositories.memories import recall_memories

            memories = await recall_memories(pool, self._project_id, limit=5)
        except Exception as exc:
            logger.warning("code_target_memory_recall_failed: %s", exc)
            return ""
        if not memories:
            return ""
        lines = "\n".join(f"- [{m['kind']}] {m['content']}" for m in memories)
        return f"## Relevant Past Learnings\n{lines}"

    def get_editable_files(self) -> list[Path]:
        """Return Python files in src/silkroute/ that the agent can edit."""
        src_dir = self._root / "src" / "silkroute"
        files = sorted(src_dir.rglob("*.py"))
        # Exclude autoresearch module itself (no recursive self-improvement)
        return [f for f in files if "autoresearch" not in str(f)]

    def invalidate_eval_cache(self) -> None:
        """Drop the cached pytest output (e.g. after a git reset changed the tree)."""
        self._last_eval_output = None

    async def _ensure_eval_output(self) -> str:
        """Return the cached pytest output, running the suite once if cold."""
        if self._last_eval_output is None:
            self._last_eval_output = await self._run_pytest_subprocess()
        return self._last_eval_output

    async def _run_pytest_subprocess(self) -> str:
        """Run the combined pytest --cov command once, return raw stdout.

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
        stdout, _ = await asyncio.wait_for(proc.communicate(), timeout=120)
        return stdout.decode(errors="replace")

    @staticmethod
    def _parse_pytest_output(output: str) -> tuple[dict, float]:
        """Parse pass/fail counts and coverage percent from a pytest --cov run's output."""
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

    # Coverage-table rows in the combined --cov output: header, per-file rows,
    # separators, and the TOTAL line. Filtered out of the test summary so the
    # pass/fail lines aren't pushed out of the last-30-lines window.
    _COVERAGE_ROW_RE = re.compile(r"^(Name\s+Stmts|src/\S+\s+\d+|TOTAL\s+\d+|-{5,})")

    async def _get_test_summary(self) -> str:
        """Get a brief test summary for LLM context (parsed from the cached eval run)."""
        output = await self._ensure_eval_output()
        lines = [
            line for line in output.strip().splitlines()
            if not self._COVERAGE_ROW_RE.match(line)
        ]
        # Return last 30 lines (summary + failures)
        return "\n".join(lines[-30:])

    async def _get_coverage_gaps(self) -> str:
        """Get files with coverage below 80% for LLM context (from the cached eval run)."""
        output = await self._ensure_eval_output()

        # Find lines with coverage < 80%
        low_cov: list[str] = []
        for line in output.splitlines():
            cov_match = re.match(r"(src/\S+)\s+\d+\s+\d+\s+(\d+)%\s*(.*)", line)
            if cov_match and int(cov_match.group(2)) < 80:
                low_cov.append(line.strip())

        return "\n".join(low_cov[:15]) if low_cov else ""
