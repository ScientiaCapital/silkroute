"""Ledger — TSV-based experiment results tracking.

Like Karpathy's results.tsv: one row per experiment, tab-separated,
with commit hash, score, status, and description.
"""

from __future__ import annotations

import csv
from dataclasses import asdict, dataclass
from pathlib import Path

_FIELDNAMES = ["commit", "score", "pass_rate", "coverage", "status", "description"]
_DELIMITER = "\t"


@dataclass
class LedgerEntry:
    """A single experiment result."""

    commit: str       # Short git commit hash (7 chars)
    score: float      # Composite metric score
    pass_rate: float  # Test pass rate 0.0–1.0
    coverage: float   # Coverage fraction 0.0–1.0
    status: str       # "keep", "discard", or "crash"
    description: str  # What this experiment tried


class Ledger:
    """Read/write experiment results in TSV format."""

    def __init__(self, path: Path) -> None:
        self._path = path

    @property
    def path(self) -> Path:
        return self._path

    def ensure_exists(self) -> None:
        """Create the TSV file with header if it doesn't exist."""
        if self._path.exists():
            return
        self._path.parent.mkdir(parents=True, exist_ok=True)
        with self._path.open("w", newline="") as f:
            writer = csv.DictWriter(f, fieldnames=_FIELDNAMES, delimiter=_DELIMITER)
            writer.writeheader()

    def append(self, entry: LedgerEntry) -> None:
        """Append an experiment result to the ledger."""
        self.ensure_exists()
        with self._path.open("a", newline="") as f:
            writer = csv.DictWriter(f, fieldnames=_FIELDNAMES, delimiter=_DELIMITER)
            writer.writerow(asdict(entry))

    def read(self) -> list[LedgerEntry]:
        """Read all entries from the ledger."""
        if not self._path.exists():
            return []
        entries: list[LedgerEntry] = []
        with self._path.open(newline="") as f:
            reader = csv.DictReader(f, delimiter=_DELIMITER)
            for row in reader:
                entries.append(LedgerEntry(
                    commit=row["commit"],
                    score=float(row["score"]),
                    pass_rate=float(row["pass_rate"]),
                    coverage=float(row["coverage"]),
                    status=row["status"],
                    description=row["description"],
                ))
        return entries

    def recent(self, n: int = 5) -> list[LedgerEntry]:
        """Return the last N entries."""
        return self.read()[-n:]

    def best(self) -> LedgerEntry | None:
        """Return the entry with the highest score."""
        entries = [e for e in self.read() if e.status == "keep"]
        if not entries:
            return None
        return max(entries, key=lambda e: e.score)

    def count(self) -> dict[str, int]:
        """Count entries by status."""
        entries = self.read()
        counts = {"keep": 0, "discard": 0, "crash": 0, "total": len(entries)}
        for e in entries:
            if e.status in counts:
                counts[e.status] += 1
        return counts
