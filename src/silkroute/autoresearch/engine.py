"""ResearchEngine — the autonomous experiment loop.

The heart of autoresearch. Loops forever: propose a change via Chinese LLM,
apply it, evaluate, keep or discard, log to ledger, repeat.
Inspired by Karpathy's autoresearch: modify → run → eval → keep/discard.
"""

from __future__ import annotations

import asyncio
import logging
import signal
import subprocess
import time
from dataclasses import asdict
from datetime import UTC, datetime
from pathlib import Path

import asyncpg
from rich.console import Console

from silkroute.autoresearch.ledger import Ledger, LedgerEntry
from silkroute.autoresearch.llm import ProposedChange, propose_change
from silkroute.autoresearch.metrics import Metrics
from silkroute.autoresearch.program import load_program
from silkroute.autoresearch.targets.base import ResearchTarget
from silkroute.config.settings import MemoryConfig

logger = logging.getLogger(__name__)
console = Console()

_MAX_CONSECUTIVE_CRASHES = 3
_SLEEP_BETWEEN_EXPERIMENTS = 2  # seconds
# Scores are ratios of ints, so identical repo states produce bit-identical
# floats. This epsilon only guards against float noise; the smallest real
# score delta (one test flipping out of ~1000) is ~6e-4, far above it.
_SCORE_EPSILON = 1e-9


class ResearchEngine:
    """Autonomous experiment loop for a research target."""

    def __init__(
        self,
        target: ResearchTarget,
        model_id: str,
        project_root: Path,
        max_experiments: int = 0,
        project_id: str = "default",
        experiment_timeout_seconds: float = 600.0,
        max_hours: float = 0.0,
    ) -> None:
        self._target = target
        self._model_id = model_id
        self._root = project_root
        self._max_experiments = max_experiments  # 0 = infinite
        self._project_id = project_id
        self._experiment_timeout_seconds = experiment_timeout_seconds  # 0 = no per-exp cap
        self._max_hours = max_hours  # 0 = no wall-clock cap
        self._ledger = Ledger(
            project_root / ".silkroute" / "autoresearch" / "results.tsv"
        )
        self._program = load_program(target.name)
        self._should_stop = False
        self._baseline: Metrics | None = None
        self._branch_name: str = ""
        self._experiment_count = 0
        self._consecutive_crashes = 0
        self._pool: asyncpg.Pool | None = None
        self._memory_enabled = MemoryConfig().enabled
        # Commit created by the current experiment, before it's known good.
        # Rolled back by the crash/timeout handlers (a plain revert-if-dirty
        # can't undo an already-made commit).
        self._pending_commit: str | None = None

    @property
    def ledger(self) -> Ledger:
        return self._ledger

    async def run(self) -> None:
        """Run the experiment loop.

        1. Create experiment branch
        2. Establish baseline
        3. Loop: propose → apply → eval → keep/discard → log

        Timeout note: the per-experiment timeout uses asyncio.wait_for, which
        can only cancel at await points. The long awaits — propose_change() (LLM
        call) and evaluate() (async subprocess) — are cancellable, which is
        where time actually goes; the sub-second blocking git subprocess.run
        calls are not. A cancelled pytest child may keep running until its own
        inner 120s bound. The --hours cap is checked between experiments only.
        """
        self._setup_signal_handlers()
        self._branch_name = self._create_branch()
        self._ledger.ensure_exists()

        # Persistent memory (optional — non-fatal if disabled or DB unavailable).
        # Mirrors agent/loop.py's Step 3b pattern.
        if self._memory_enabled:
            try:
                from silkroute.db.pool import get_pool

                self._pool = await get_pool()
            except (ImportError, asyncpg.PostgresError, OSError, TimeoutError) as exc:
                logger.warning("autoresearch_memory_pool_unavailable: %s", exc)

        console.print("\n[bold]AutoResearch Engine[/bold]")
        console.print(f"  Target: {self._target.name}")
        console.print(f"  Model: {self._model_id}")
        console.print(f"  Branch: {self._branch_name}")
        console.print(f"  Ledger: {self._ledger.path}")
        if self._max_experiments > 0:
            console.print(f"  Max experiments: {self._max_experiments}")
        else:
            console.print("  Max experiments: unlimited (Ctrl+C to stop)")
        console.print()

        # Establish baseline
        console.print("[dim]Establishing baseline...[/dim]")
        self._baseline = await self._target.evaluate()
        baseline_commit = self._git_short_hash()
        self._ledger.append(LedgerEntry(
            commit=baseline_commit,
            score=self._baseline.score,
            pass_rate=self._baseline.pass_rate,
            coverage=self._baseline.coverage_pct,
            status="keep",
            description="baseline",
        ))
        console.print(f"  Baseline: {self._baseline.summary()}\n")

        run_start = time.monotonic()

        # Main loop
        while not self._should_stop:
            if self._max_experiments > 0 and self._experiment_count >= self._max_experiments:
                console.print(
                    f"\n[green]Reached max experiments "
                    f"({self._max_experiments}). Stopping.[/green]"
                )
                break

            # Wall-clock cap (checked between experiments — may overshoot by up
            # to one experiment's duration).
            if self._max_hours > 0 and (time.monotonic() - run_start) >= self._max_hours * 3600:
                console.print(
                    f"\n[green]Reached wall-clock cap "
                    f"(--hours {self._max_hours}). Stopping.[/green]"
                )
                break

            self._experiment_count += 1
            console.print(f"[bold]── Experiment {self._experiment_count} ──[/bold]")

            try:
                await asyncio.wait_for(
                    self._run_one_experiment(),
                    timeout=self._experiment_timeout_seconds or None,
                )
                self._consecutive_crashes = 0
            except KeyboardInterrupt:
                console.print("\n[yellow]Interrupted. Cleaning up...[/yellow]")
                self._rollback_experiment()
                break
            except TimeoutError:
                timeout_s = int(self._experiment_timeout_seconds)
                console.print(f"  [red]TIMEOUT after {timeout_s}s[/red]")
                if await self._handle_failed_experiment(
                    f"crash: timeout after {timeout_s}s", "timeout",
                ):
                    break
            except Exception as e:
                logger.exception("Experiment crashed: %s", e)
                console.print(f"  [red]CRASH: {e}[/red]")
                if await self._handle_failed_experiment(
                    f"crash: {str(e)[:80]}", str(e)[:80],
                ):
                    break

            await asyncio.sleep(_SLEEP_BETWEEN_EXPERIMENTS)

        self._print_summary()

    async def _handle_failed_experiment(self, description: str, memory_reason: str) -> bool:
        """Shared crash/timeout handling. Returns True if the circuit breaker tripped.

        Rolls back any pending commit, logs a crash ledger row + memory, and
        bumps the consecutive-crash counter.
        """
        self._consecutive_crashes += 1
        self._rollback_experiment()

        self._ledger.append(LedgerEntry(
            commit=self._git_short_hash(),
            score=0.0,
            pass_rate=0.0,
            coverage=0.0,
            status="crash",
            description=description,
        ))
        await self._record_outcome_memory("crash", memory_reason, 0.0, importance=0.2)

        if self._consecutive_crashes >= _MAX_CONSECUTIVE_CRASHES:
            console.print(
                f"\n[red bold]{_MAX_CONSECUTIVE_CRASHES} consecutive crashes. "
                f"Pausing to avoid spinning.[/red bold]"
            )
            return True
        return False

    def _rollback_experiment(self) -> None:
        """Undo an in-flight experiment: discard uncommitted edits and, if the
        experiment already committed, reset that commit off the branch.
        """
        self._revert_if_dirty()
        if self._pending_commit and self._git_short_hash() == self._pending_commit:
            self._git_reset()
        self._pending_commit = None
        self._target.invalidate_eval_cache()

    async def stop(self) -> None:
        """Signal graceful shutdown after current experiment."""
        self._should_stop = True

    async def _run_one_experiment(self) -> None:
        """Run a single experiment: propose → apply → eval → keep/discard."""
        # Build context
        recent = self._ledger.recent(5)
        recent_dicts = [asdict(e) for e in recent]
        context = await self._target.build_context(recent_dicts)

        # Get editable files
        editable = self._target.get_editable_files()

        # Propose change
        console.print("  [dim]Asking LLM for a change...[/dim]")
        change = await propose_change(
            model_id=self._model_id,
            program=self._program,
            context=context,
            target_files=editable[:20],  # Limit files sent to LLM
            allowed_paths=self._target.allowed_paths,
            max_diff_lines=self._target.max_diff_lines,
        )
        console.print(f"  Proposal: {change.rationale}")

        # Validate and apply
        self._validate_change(change)
        self._apply_change(change)
        commit_hash = self._git_commit(
            f"experiment: {change.rationale}",
            files=[change.file_path],
        )
        self._pending_commit = commit_hash

        # Evaluate
        console.print("  [dim]Evaluating...[/dim]")
        metrics = await self._target.evaluate()
        console.print(f"  Result: {metrics.summary()}")

        # Compare to baseline
        keep, is_simplification = self._should_keep(metrics, change)
        if keep:
            # KEEP — advance branch
            if is_simplification:
                old_n = change.old_code.count("\n")
                new_n = change.new_code.count("\n")
                console.print(
                    f"  [green bold]KEEP[/green bold] — equal score, simpler code "
                    f"({old_n} → {new_n} lines)"
                )
                description = f"simplify: {change.rationale}"
            else:
                console.print(
                    f"  [green bold]KEEP[/green bold] — score improved "
                    f"{self._baseline.score:.4f} → {metrics.score:.4f}"
                )
                description = change.rationale
            self._baseline = metrics
            self._ledger.append(LedgerEntry(
                commit=commit_hash,
                score=metrics.score,
                pass_rate=metrics.pass_rate,
                coverage=metrics.coverage_pct,
                status="keep",
                description=description,
            ))
            await self._record_outcome_memory(
                "keep", description, metrics.score, importance=0.6,
            )
        else:
            # DISCARD — revert
            console.print(
                f"  [yellow]DISCARD[/yellow] — score "
                f"{metrics.score:.4f} <= baseline {self._baseline.score:.4f}"
            )
            self._git_reset()
            # Cache holds the discarded candidate's eval output — stale now
            self._target.invalidate_eval_cache()
            self._ledger.append(LedgerEntry(
                commit=commit_hash,
                score=metrics.score,
                pass_rate=metrics.pass_rate,
                coverage=metrics.coverage_pct,
                status="discard",
                description=change.rationale,
            ))
            await self._record_outcome_memory(
                "discard", change.rationale, metrics.score, importance=0.3,
            )
        self._pending_commit = None

    def _should_keep(self, metrics: Metrics, change: ProposedChange) -> tuple[bool, bool]:
        """Decide whether to keep a candidate. Returns (keep, is_simplification).

        Keep if the score strictly improved, OR — mirroring Karpathy's elegance
        rule — the score is equal (within epsilon) but the change strictly
        reduced line count. "A small improvement that adds ugly complexity is
        not worth it": deleting code while holding the score is a win.
        """
        if metrics.is_better_than(self._baseline):
            return True, False
        equal_score = abs(metrics.score - self._baseline.score) <= _SCORE_EPSILON
        simpler = change.new_code.count("\n") < change.old_code.count("\n")
        if equal_score and simpler:
            return True, True
        return False, False

    async def _record_outcome_memory(
        self, status: str, rationale: str, score: float, importance: float,
    ) -> None:
        """Persist an outcome memory. Fail-open — never affects git/ledger state.

        Called after the ledger append (and any git commit/reset) has already
        happened, so a memory-store failure here can't roll back real state.
        """
        if self._pool is None or not self._memory_enabled:
            return
        try:
            from silkroute.db.repositories.memories import insert_memory

            await insert_memory(
                self._pool,
                f"{status}: {rationale} (score {score:.4f})",
                kind="outcome",
                project_id=self._project_id,
                importance=importance,
            )
        except Exception as exc:
            logger.warning("autoresearch_memory_insert_failed: %s", exc)

    def _validate_change(self, change: ProposedChange) -> None:
        """Validate the proposed change is within bounds."""
        # Check file is in allowed paths
        if not any(change.file_path.startswith(p) for p in self._target.allowed_paths):
            raise ValueError(
                f"File {change.file_path} not in allowed paths: "
                f"{self._target.allowed_paths}"
            )

        # Check file exists
        full_path = self._root / change.file_path
        if not full_path.exists():
            raise ValueError(f"File does not exist: {change.file_path}")

        # Check old_code exists in file
        content = full_path.read_text()
        if change.old_code not in content:
            raise ValueError(
                f"old_code not found in {change.file_path}. "
                f"LLM may have hallucinated the code."
            )

        # Check diff size
        new_lines = change.new_code.count("\n")
        old_lines = change.old_code.count("\n")
        diff_size = abs(new_lines - old_lines) + max(new_lines, old_lines)
        if diff_size > self._target.max_diff_lines:
            raise ValueError(
                f"Diff too large: {diff_size} lines "
                f"(max {self._target.max_diff_lines})"
            )

    def _apply_change(self, change: ProposedChange) -> None:
        """Apply the proposed change to the file."""
        full_path = self._root / change.file_path
        content = full_path.read_text()
        new_content = content.replace(change.old_code, change.new_code, 1)
        full_path.write_text(new_content)

    def _create_branch(self) -> str:
        """Create a new experiment branch from current HEAD."""
        date_str = datetime.now(UTC).strftime("%Y%m%d")
        branch = f"autoresearch/{self._target.name}-{date_str}"

        # Check if branch exists, append suffix if needed
        result = subprocess.run(
            ["git", "branch", "--list", branch],
            cwd=str(self._root),
            capture_output=True, text=True,
        )
        if result.stdout.strip():
            # Branch exists, check it out
            subprocess.run(
                ["git", "checkout", branch],
                cwd=str(self._root),
                capture_output=True, text=True, check=True,
            )
        else:
            subprocess.run(
                ["git", "checkout", "-b", branch],
                cwd=str(self._root),
                capture_output=True, text=True, check=True,
            )
        return branch

    def _git_commit(self, message: str, files: list[str] | None = None) -> str:
        """Stage specific files and commit. Returns short hash."""
        add_cmd = ["git", "add"] + (files if files else ["-A"])
        subprocess.run(
            add_cmd,
            cwd=str(self._root),
            capture_output=True, text=True, check=True,
        )
        subprocess.run(
            ["git", "commit", "-m", message],
            cwd=str(self._root),
            capture_output=True, text=True, check=True,
        )
        return self._git_short_hash()

    def _git_reset(self) -> None:
        """Reset to previous commit (discard last experiment)."""
        subprocess.run(
            ["git", "reset", "--hard", "HEAD~1"],
            cwd=str(self._root),
            capture_output=True, text=True, check=True,
        )

    def _git_short_hash(self) -> str:
        """Get the short hash of HEAD."""
        result = subprocess.run(
            ["git", "rev-parse", "--short", "HEAD"],
            cwd=str(self._root),
            capture_output=True, text=True, check=True,
        )
        return result.stdout.strip()

    def _revert_if_dirty(self) -> None:
        """Revert any uncommitted changes."""
        result = subprocess.run(
            ["git", "status", "--porcelain"],
            cwd=str(self._root),
            capture_output=True, text=True,
        )
        if result.stdout.strip():
            subprocess.run(
                ["git", "checkout", "."],
                cwd=str(self._root),
                capture_output=True, text=True,
            )

    def _setup_signal_handlers(self) -> None:
        """Set up graceful shutdown on SIGINT/SIGTERM."""
        loop = asyncio.get_event_loop()
        for sig in (signal.SIGINT, signal.SIGTERM):
            loop.add_signal_handler(sig, self._handle_signal)

    def _handle_signal(self) -> None:
        """Handle shutdown signal."""
        console.print(
            "\n[yellow]Shutdown signal received. "
            "Finishing current experiment...[/yellow]"
        )
        self._should_stop = True

    def _print_summary(self) -> None:
        """Print final summary of the research session."""
        counts = self._ledger.count()
        best = self._ledger.best()

        console.print("\n[bold]AutoResearch Summary[/bold]")
        console.print(f"  Experiments: {counts['total']}")
        console.print(f"  Kept: {counts['keep']}")
        console.print(f"  Discarded: {counts['discard']}")
        console.print(f"  Crashed: {counts['crash']}")
        if best:
            console.print(f"  Best score: {best.score:.4f} ({best.description})")
        console.print(f"  Branch: {self._branch_name}")
        console.print(f"  Ledger: {self._ledger.path}")
