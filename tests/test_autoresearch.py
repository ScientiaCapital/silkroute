"""Tests for the autoresearch module."""

from __future__ import annotations

import json
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from silkroute.autoresearch.ledger import Ledger, LedgerEntry
from silkroute.autoresearch.llm import ProposedChange, _parse_response
from silkroute.autoresearch.metrics import Metrics
from silkroute.autoresearch.program import list_programs, load_program


# ── Metrics ──────────────────────────────────────────────────────────


class TestMetrics:
    def test_score_all_perfect(self) -> None:
        m = Metrics(
            pass_rate=1.0, coverage_pct=1.0, lint_clean=True,
            total_tests=100, tests_passed=100, tests_failed=0,
            error_summary="",
        )
        assert m.score == pytest.approx(1.0)

    def test_score_all_zero(self) -> None:
        m = Metrics(
            pass_rate=0.0, coverage_pct=0.0, lint_clean=False,
            total_tests=100, tests_passed=0, tests_failed=100,
            error_summary="everything failed",
        )
        assert m.score == pytest.approx(0.0)

    def test_score_partial(self) -> None:
        m = Metrics(
            pass_rate=0.8, coverage_pct=0.5, lint_clean=True,
            total_tests=100, tests_passed=80, tests_failed=20,
            error_summary="20 failures",
        )
        # 0.8*0.6 + 0.5*0.3 + 1.0*0.1 = 0.48 + 0.15 + 0.1 = 0.73
        assert m.score == pytest.approx(0.73)

    def test_is_better_than(self) -> None:
        better = Metrics(
            pass_rate=0.9, coverage_pct=0.8, lint_clean=True,
            total_tests=100, tests_passed=90, tests_failed=10,
            error_summary="",
        )
        worse = Metrics(
            pass_rate=0.5, coverage_pct=0.3, lint_clean=False,
            total_tests=100, tests_passed=50, tests_failed=50,
            error_summary="",
        )
        assert better.is_better_than(worse)
        assert not worse.is_better_than(better)
        assert not better.is_better_than(better)  # Equal is not better

    def test_summary(self) -> None:
        m = Metrics(
            pass_rate=0.95, coverage_pct=0.82, lint_clean=True,
            total_tests=200, tests_passed=190, tests_failed=10,
            error_summary="",
        )
        s = m.summary()
        assert "score=" in s
        assert "pass=190/200" in s
        assert "cov=82.0%" in s
        assert "lint=clean" in s

    def test_summary_lint_dirty(self) -> None:
        m = Metrics(
            pass_rate=1.0, coverage_pct=1.0, lint_clean=False,
            total_tests=1, tests_passed=1, tests_failed=0,
            error_summary="",
        )
        assert "lint=dirty" in m.summary()

    def test_frozen(self) -> None:
        m = Metrics(
            pass_rate=1.0, coverage_pct=1.0, lint_clean=True,
            total_tests=1, tests_passed=1, tests_failed=0,
            error_summary="",
        )
        with pytest.raises(AttributeError):
            m.pass_rate = 0.5  # type: ignore[misc]


# ── Ledger ───────────────────────────────────────────────────────────


class TestLedger:
    def test_ensure_creates_file(self, tmp_path: Path) -> None:
        ledger = Ledger(tmp_path / "sub" / "results.tsv")
        ledger.ensure_exists()
        assert ledger.path.exists()
        content = ledger.path.read_text()
        assert "commit" in content
        assert "score" in content

    def test_append_and_read(self, tmp_path: Path) -> None:
        ledger = Ledger(tmp_path / "results.tsv")
        entry = LedgerEntry(
            commit="abc1234",
            score=0.85,
            pass_rate=0.9,
            coverage=0.75,
            status="keep",
            description="improved error handling",
        )
        ledger.append(entry)

        entries = ledger.read()
        assert len(entries) == 1
        assert entries[0].commit == "abc1234"
        assert entries[0].score == pytest.approx(0.85)
        assert entries[0].status == "keep"

    def test_recent(self, tmp_path: Path) -> None:
        ledger = Ledger(tmp_path / "results.tsv")
        for i in range(10):
            ledger.append(LedgerEntry(
                commit=f"hash{i:03d}",
                score=float(i) / 10,
                pass_rate=0.5,
                coverage=0.5,
                status="keep" if i % 2 == 0 else "discard",
                description=f"experiment {i}",
            ))

        recent = ledger.recent(3)
        assert len(recent) == 3
        assert recent[0].commit == "hash007"
        assert recent[2].commit == "hash009"

    def test_best(self, tmp_path: Path) -> None:
        ledger = Ledger(tmp_path / "results.tsv")
        ledger.append(LedgerEntry("aaa", 0.5, 0.5, 0.5, "keep", "first"))
        ledger.append(LedgerEntry("bbb", 0.9, 0.9, 0.9, "keep", "best"))
        ledger.append(LedgerEntry("ccc", 0.95, 0.95, 0.95, "discard", "discarded high"))
        ledger.append(LedgerEntry("ddd", 0.7, 0.7, 0.7, "keep", "third"))

        best = ledger.best()
        assert best is not None
        assert best.commit == "bbb"
        assert best.score == pytest.approx(0.9)

    def test_best_empty(self, tmp_path: Path) -> None:
        ledger = Ledger(tmp_path / "results.tsv")
        assert ledger.best() is None

    def test_count(self, tmp_path: Path) -> None:
        ledger = Ledger(tmp_path / "results.tsv")
        ledger.append(LedgerEntry("a", 0.5, 0.5, 0.5, "keep", "a"))
        ledger.append(LedgerEntry("b", 0.3, 0.3, 0.3, "discard", "b"))
        ledger.append(LedgerEntry("c", 0.0, 0.0, 0.0, "crash", "c"))
        ledger.append(LedgerEntry("d", 0.6, 0.6, 0.6, "keep", "d"))

        counts = ledger.count()
        assert counts == {"keep": 2, "discard": 1, "crash": 1, "total": 4}

    def test_read_nonexistent(self, tmp_path: Path) -> None:
        ledger = Ledger(tmp_path / "nope.tsv")
        assert ledger.read() == []


# ── LLM Response Parsing ─────────────────────────────────────────────


class TestParseResponse:
    def test_valid_json(self) -> None:
        response = json.dumps({
            "file_path": "src/silkroute/cli.py",
            "old_code": "def foo():",
            "new_code": "def foo() -> None:",
            "rationale": "add return type hint",
        })
        change = _parse_response(response)
        assert isinstance(change, ProposedChange)
        assert change.file_path == "src/silkroute/cli.py"
        assert change.rationale == "add return type hint"

    def test_json_in_code_fence(self) -> None:
        response = '```json\n{"file_path": "a.py", "old_code": "x", "new_code": "y", "rationale": "fix"}\n```'
        change = _parse_response(response)
        assert change.file_path == "a.py"

    def test_invalid_json(self) -> None:
        with pytest.raises(ValueError, match="not valid JSON"):
            _parse_response("this is not json")

    def test_missing_fields(self) -> None:
        response = json.dumps({"file_path": "a.py", "old_code": "x"})
        with pytest.raises(ValueError, match="missing required fields"):
            _parse_response(response)

    def test_noop_change(self) -> None:
        response = json.dumps({
            "file_path": "a.py",
            "old_code": "same",
            "new_code": "same",
            "rationale": "no change",
        })
        with pytest.raises(ValueError, match="no-op"):
            _parse_response(response)


# ── Program Loading ──────────────────────────────────────────────────


class TestProgram:
    def test_load_code_program(self) -> None:
        program = load_program("code")
        assert "SilkRoute Code Improver" in program
        assert "autonomous researcher" in program

    def test_load_nonexistent(self) -> None:
        with pytest.raises(FileNotFoundError, match="nonexistent"):
            load_program("nonexistent")

    def test_list_programs(self) -> None:
        programs = list_programs()
        assert "code" in programs


# ── Engine ───────────────────────────────────────────────────────────


class TestEngine:
    @pytest.mark.asyncio
    async def test_engine_keep_on_improvement(self, tmp_path: Path) -> None:
        """Engine keeps changes when metrics improve."""
        from silkroute.autoresearch.engine import ResearchEngine

        target = MagicMock()
        target.name = "code"
        target.allowed_paths = ["src/"]
        target.max_diff_lines = 50
        target.get_editable_files = MagicMock(return_value=[])

        # Baseline metrics
        baseline = Metrics(
            pass_rate=0.8, coverage_pct=0.5, lint_clean=True,
            total_tests=100, tests_passed=80, tests_failed=20,
            error_summary="",
        )
        # Improved metrics
        improved = Metrics(
            pass_rate=0.9, coverage_pct=0.6, lint_clean=True,
            total_tests=100, tests_passed=90, tests_failed=10,
            error_summary="",
        )
        target.evaluate = AsyncMock(side_effect=[baseline, improved])
        target.build_context = AsyncMock(return_value="test context")

        engine = ResearchEngine(
            target=target,
            model_id="test-model",
            project_root=tmp_path,
            max_experiments=1,
        )

        # Mock git and LLM
        with patch.object(engine, "_create_branch", return_value="autoresearch/test"), \
             patch.object(engine, "_git_short_hash", return_value="abc1234"), \
             patch.object(engine, "_git_commit", return_value="def5678"), \
             patch.object(engine, "_git_reset") as mock_reset, \
             patch.object(engine, "_setup_signal_handlers"), \
             patch("silkroute.autoresearch.engine.propose_change", new_callable=AsyncMock) as mock_propose, \
             patch.object(engine, "_validate_change"), \
             patch.object(engine, "_apply_change"):

            mock_propose.return_value = ProposedChange(
                file_path="src/test.py",
                old_code="old",
                new_code="new",
                rationale="improved something",
            )

            await engine.run()

        # Should NOT have reset (change was kept)
        mock_reset.assert_not_called()
        # Ledger should have 2 entries: baseline + kept experiment
        entries = engine.ledger.read()
        assert len(entries) == 2
        assert entries[0].status == "keep"  # baseline
        assert entries[1].status == "keep"  # improvement

    @pytest.mark.asyncio
    async def test_engine_discard_on_regression(self, tmp_path: Path) -> None:
        """Engine discards changes when metrics regress."""
        from silkroute.autoresearch.engine import ResearchEngine

        target = MagicMock()
        target.name = "code"
        target.allowed_paths = ["src/"]
        target.max_diff_lines = 50
        target.get_editable_files = MagicMock(return_value=[])

        baseline = Metrics(
            pass_rate=0.9, coverage_pct=0.8, lint_clean=True,
            total_tests=100, tests_passed=90, tests_failed=10,
            error_summary="",
        )
        worse = Metrics(
            pass_rate=0.7, coverage_pct=0.6, lint_clean=True,
            total_tests=100, tests_passed=70, tests_failed=30,
            error_summary="",
        )
        target.evaluate = AsyncMock(side_effect=[baseline, worse])
        target.build_context = AsyncMock(return_value="context")

        engine = ResearchEngine(
            target=target,
            model_id="test-model",
            project_root=tmp_path,
            max_experiments=1,
        )

        with patch.object(engine, "_create_branch", return_value="autoresearch/test"), \
             patch.object(engine, "_git_short_hash", return_value="abc1234"), \
             patch.object(engine, "_git_commit", return_value="def5678"), \
             patch.object(engine, "_git_reset") as mock_reset, \
             patch.object(engine, "_setup_signal_handlers"), \
             patch("silkroute.autoresearch.engine.propose_change", new_callable=AsyncMock) as mock_propose, \
             patch.object(engine, "_validate_change"), \
             patch.object(engine, "_apply_change"):

            mock_propose.return_value = ProposedChange(
                file_path="src/test.py",
                old_code="old",
                new_code="new",
                rationale="broke something",
            )

            await engine.run()

        # Should have reset (change was discarded)
        mock_reset.assert_called_once()
        entries = engine.ledger.read()
        assert entries[1].status == "discard"

    @pytest.mark.asyncio
    async def test_engine_crash_circuit_breaker(self, tmp_path: Path) -> None:
        """Engine stops after 3 consecutive crashes."""
        from silkroute.autoresearch.engine import ResearchEngine

        target = MagicMock()
        target.name = "code"
        target.allowed_paths = ["src/"]
        target.max_diff_lines = 50
        target.get_editable_files = MagicMock(return_value=[])

        baseline = Metrics(
            pass_rate=0.9, coverage_pct=0.8, lint_clean=True,
            total_tests=100, tests_passed=90, tests_failed=10,
            error_summary="",
        )
        target.evaluate = AsyncMock(return_value=baseline)
        target.build_context = AsyncMock(side_effect=RuntimeError("boom"))

        engine = ResearchEngine(
            target=target,
            model_id="test-model",
            project_root=tmp_path,
            max_experiments=10,
        )

        with patch.object(engine, "_create_branch", return_value="autoresearch/test"), \
             patch.object(engine, "_git_short_hash", return_value="abc1234"), \
             patch.object(engine, "_setup_signal_handlers"), \
             patch.object(engine, "_revert_if_dirty"):

            await engine.run()

        # Should have stopped after 3 crashes + 1 baseline
        entries = engine.ledger.read()
        crash_entries = [e for e in entries if e.status == "crash"]
        assert len(crash_entries) == 3


# ── Code Improver Target ─────────────────────────────────────────────


class TestCodeImproverTarget:
    def test_get_editable_files(self, tmp_path: Path) -> None:
        from silkroute.autoresearch.targets.code import CodeImproverTarget

        # Create some test files
        src = tmp_path / "src" / "silkroute"
        src.mkdir(parents=True)
        (src / "cli.py").write_text("# cli")
        (src / "config" / "settings.py").parent.mkdir()
        (src / "config" / "settings.py").write_text("# settings")

        # Create autoresearch files (should be excluded)
        ar = src / "autoresearch"
        ar.mkdir()
        (ar / "engine.py").write_text("# engine")

        target = CodeImproverTarget(tmp_path)
        files = target.get_editable_files()

        file_names = [f.name for f in files]
        assert "cli.py" in file_names
        assert "settings.py" in file_names
        assert "engine.py" not in file_names  # excluded
