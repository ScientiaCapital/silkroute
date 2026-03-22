"""Metrics — evaluation results from a research experiment."""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class Metrics:
    """Composite evaluation metrics for a single experiment run.

    The score is a weighted composite:
      pass_rate * 0.6 + coverage_pct * 0.3 + lint_clean * 0.1
    """

    pass_rate: float       # 0.0–1.0: tests passing / total tests
    coverage_pct: float    # 0.0–1.0: line coverage fraction
    lint_clean: bool       # True if ruff exits 0
    total_tests: int       # Total number of tests collected
    tests_passed: int      # Number of tests that passed
    tests_failed: int      # Number of tests that failed
    error_summary: str     # Brief summary of failures (empty if clean)

    @property
    def score(self) -> float:
        """Composite score — higher is better."""
        lint_score = 1.0 if self.lint_clean else 0.0
        return (self.pass_rate * 0.6) + (self.coverage_pct * 0.3) + (lint_score * 0.1)

    def is_better_than(self, other: Metrics) -> bool:
        """True if this metric set is strictly better than another."""
        return self.score > other.score

    def summary(self) -> str:
        """One-line summary for logging."""
        lint_icon = "clean" if self.lint_clean else "dirty"
        return (
            f"score={self.score:.4f} "
            f"pass={self.tests_passed}/{self.total_tests} "
            f"cov={self.coverage_pct:.1%} "
            f"lint={lint_icon}"
        )
