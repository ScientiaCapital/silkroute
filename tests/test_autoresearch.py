"""Tests for the autoresearch module."""

from __future__ import annotations

import asyncio
import json
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from silkroute.autoresearch.ledger import Ledger, LedgerEntry
from silkroute.autoresearch.llm import ProposedChange, _parse_response, propose_change
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

    def test_extracts_embedded_json(self) -> None:
        # Local models love to prepend prose before the JSON.
        response = (
            'Sure! Here is the JSON for my proposed change:\n'
            '{"file_path": "a.py", "old_code": "x", "new_code": "y", "rationale": "fix"}\n'
            'Let me know if you need anything else.'
        )
        change = _parse_response(response)
        assert change.file_path == "a.py"
        assert change.rationale == "fix"


# ── Ollama researcher path ───────────────────────────────────────────


class TestOllamaResearcher:
    @pytest.mark.asyncio
    async def test_ollama_uses_litellm_no_api_key(self, tmp_path: Path, monkeypatch) -> None:
        monkeypatch.delenv("OPENROUTER_API_KEY", raising=False)
        monkeypatch.delenv("SILKROUTE_OPENROUTER_API_KEY", raising=False)

        f = tmp_path / "mod.py"
        f.write_text("def foo():\n    pass\n")

        canned = json.dumps({
            "file_path": "mod.py", "old_code": "pass", "new_code": "return 1",
            "rationale": "return a value",
        })
        fake_response = MagicMock()
        fake_response.choices = [MagicMock(message=MagicMock(content=canned))]

        with patch("litellm.acompletion", new_callable=AsyncMock, return_value=fake_response) as mock_acomp:
            change = await propose_change(
                model_id="ollama/qwen2.5:14b",
                program="be a researcher",
                context="ctx",
                target_files=[f],
                allowed_paths=["src/"],
                max_diff_lines=50,
            )

        assert change.file_path == "mod.py"
        _, kwargs = mock_acomp.call_args
        assert kwargs["model"] == "ollama/qwen2.5:14b"
        assert kwargs["api_base"] == "http://localhost:11434"
        assert "api_key" not in kwargs

    @pytest.mark.asyncio
    async def test_openrouter_path_unchanged(self, tmp_path: Path) -> None:
        from silkroute.autoresearch import llm as llm_mod

        f = tmp_path / "mod.py"
        f.write_text("def foo():\n    pass\n")

        canned = json.dumps({
            "file_path": "mod.py", "old_code": "pass", "new_code": "return 1",
            "rationale": "return a value",
        })
        fake_llm = MagicMock()
        fake_llm.ainvoke = AsyncMock(return_value=MagicMock(content=canned))

        with patch.object(llm_mod, "create_openrouter_model", return_value=fake_llm) as mock_create:
            change = await propose_change(
                model_id="deepseek/deepseek-v3.2",
                program="be a researcher",
                context="ctx",
                target_files=[f],
                allowed_paths=["src/"],
                max_diff_lines=50,
            )

        assert change.rationale == "return a value"
        mock_create.assert_called_once()


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

        import silkroute.db.pool as pool_mod
        pool_mod._pool = None

        # Mock git and LLM
        with patch.object(engine, "_create_branch", return_value="autoresearch/test"), \
             patch.object(engine, "_git_short_hash", return_value="abc1234"), \
             patch.object(engine, "_git_commit", return_value="def5678"), \
             patch.object(engine, "_git_reset") as mock_reset, \
             patch.object(engine, "_setup_signal_handlers"), \
             patch("silkroute.autoresearch.engine.propose_change", new_callable=AsyncMock) as mock_propose, \
             patch.object(engine, "_validate_change"), \
             patch.object(engine, "_apply_change"), \
             patch(
                 "silkroute.db.pool.asyncpg.create_pool",
                 new_callable=AsyncMock, side_effect=OSError("no db in unit tests"),
             ):

            mock_propose.return_value = ProposedChange(
                file_path="src/test.py",
                old_code="old",
                new_code="new",
                rationale="improved something",
            )

            await engine.run()

        pool_mod._pool = None

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

        import silkroute.db.pool as pool_mod
        pool_mod._pool = None

        with patch.object(engine, "_create_branch", return_value="autoresearch/test"), \
             patch.object(engine, "_git_short_hash", return_value="abc1234"), \
             patch.object(engine, "_git_commit", return_value="def5678"), \
             patch.object(engine, "_git_reset") as mock_reset, \
             patch.object(engine, "_setup_signal_handlers"), \
             patch("silkroute.autoresearch.engine.propose_change", new_callable=AsyncMock) as mock_propose, \
             patch.object(engine, "_validate_change"), \
             patch.object(engine, "_apply_change"), \
             patch(
                 "silkroute.db.pool.asyncpg.create_pool",
                 new_callable=AsyncMock, side_effect=OSError("no db in unit tests"),
             ):

            mock_propose.return_value = ProposedChange(
                file_path="src/test.py",
                old_code="old",
                new_code="new",
                rationale="broke something",
            )

            await engine.run()

        pool_mod._pool = None

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

        import silkroute.db.pool as pool_mod
        pool_mod._pool = None

        with patch.object(engine, "_create_branch", return_value="autoresearch/test"), \
             patch.object(engine, "_git_short_hash", return_value="abc1234"), \
             patch.object(engine, "_setup_signal_handlers"), \
             patch.object(engine, "_revert_if_dirty"), \
             patch(
                 "silkroute.db.pool.asyncpg.create_pool",
                 new_callable=AsyncMock, side_effect=OSError("no db in unit tests"),
             ):

            await engine.run()

        pool_mod._pool = None

        # Should have stopped after 3 crashes + 1 baseline
        entries = engine.ledger.read()
        crash_entries = [e for e in entries if e.status == "crash"]
        assert len(crash_entries) == 3


# ── Eval caching (#24) ───────────────────────────────────────────────


_COMBINED_PYTEST_OUTPUT = (
    "........F.\n"
    "FAILED tests/test_x.py::test_y - assert False\n"
    "Name                        Stmts   Miss  Cover   Missing\n"
    "---------------------------------------------------------\n"
    "src/silkroute/foo.py          100     30    70%   1-30\n"
    "src/silkroute/bar.py           50      5    90%   1-5\n"
    "---------------------------------------------------------\n"
    "TOTAL                         150     35    77%\n"
    "9 passed, 1 failed\n"
)


def _make_fake_proc(stdout: str = _COMBINED_PYTEST_OUTPUT) -> MagicMock:
    proc = MagicMock()
    proc.communicate = AsyncMock(return_value=(stdout.encode(), b""))
    proc.returncode = 0
    return proc


def _pytest_calls(mock_exec: AsyncMock) -> list:
    return [c for c in mock_exec.call_args_list if "pytest" in c.args]


class TestEvalCaching:
    @pytest.mark.asyncio
    async def test_evaluate_then_build_context_single_pytest_run(self, tmp_path: Path) -> None:
        from silkroute.autoresearch.targets.code import CodeImproverTarget

        target = CodeImproverTarget(tmp_path)

        with patch(
            "silkroute.autoresearch.targets.code.asyncio.create_subprocess_exec",
            new_callable=AsyncMock, side_effect=lambda *a, **kw: _make_fake_proc(),
        ) as mock_exec, \
             patch.object(target, "_build_memory_section", new=AsyncMock(return_value="")):
            await target.evaluate()
            context = await target.build_context([])

        assert len(_pytest_calls(mock_exec)) == 1
        assert "## Current Test Status" in context

    @pytest.mark.asyncio
    async def test_build_context_falls_back_when_cache_cold(self, tmp_path: Path) -> None:
        from silkroute.autoresearch.targets.code import CodeImproverTarget

        target = CodeImproverTarget(tmp_path)

        with patch(
            "silkroute.autoresearch.targets.code.asyncio.create_subprocess_exec",
            new_callable=AsyncMock, side_effect=lambda *a, **kw: _make_fake_proc(),
        ) as mock_exec, \
             patch.object(target, "_build_memory_section", new=AsyncMock(return_value="")):
            await target.build_context([])

        assert len(_pytest_calls(mock_exec)) == 1

    @pytest.mark.asyncio
    async def test_invalidate_forces_rerun(self, tmp_path: Path) -> None:
        from silkroute.autoresearch.targets.code import CodeImproverTarget

        target = CodeImproverTarget(tmp_path)

        with patch(
            "silkroute.autoresearch.targets.code.asyncio.create_subprocess_exec",
            new_callable=AsyncMock, side_effect=lambda *a, **kw: _make_fake_proc(),
        ) as mock_exec, \
             patch.object(target, "_build_memory_section", new=AsyncMock(return_value="")):
            await target.evaluate()
            target.invalidate_eval_cache()
            await target.build_context([])

        assert len(_pytest_calls(mock_exec)) == 2

    @pytest.mark.asyncio
    async def test_summary_excludes_coverage_table(self, tmp_path: Path) -> None:
        from silkroute.autoresearch.targets.code import CodeImproverTarget

        target = CodeImproverTarget(tmp_path)
        # Pad with 40 coverage rows so the raw last-30 window would be all coverage
        padded = (
            "9 passed, 1 failed\n"
            + "\n".join(f"src/silkroute/mod{i}.py   100  30   70%   1-30" for i in range(40))
            + "\nTOTAL  4000  1200  70%\n"
        )
        target._last_eval_output = padded

        summary = await target._get_test_summary()
        assert "9 passed, 1 failed" in summary
        assert "src/silkroute/mod5.py" not in summary

    @pytest.mark.asyncio
    async def test_coverage_gaps_parse_from_cache(self, tmp_path: Path) -> None:
        from silkroute.autoresearch.targets.code import CodeImproverTarget

        target = CodeImproverTarget(tmp_path)
        target._last_eval_output = _COMBINED_PYTEST_OUTPUT

        gaps = await target._get_coverage_gaps()
        assert "src/silkroute/foo.py" in gaps   # 70% < 80
        assert "src/silkroute/bar.py" not in gaps  # 90%

    def test_parse_pytest_output(self) -> None:
        from silkroute.autoresearch.targets.code import CodeImproverTarget

        result, cov = CodeImproverTarget._parse_pytest_output(_COMBINED_PYTEST_OUTPUT)
        assert result["passed"] == 9
        assert result["failed"] == 1
        assert result["pass_rate"] == pytest.approx(0.9)
        assert cov == pytest.approx(0.77)


# ── Wall-clock budgets + simplicity keeps ────────────────────────────


def _metrics(pass_rate: float, cov: float = 0.5) -> Metrics:
    return Metrics(
        pass_rate=pass_rate, coverage_pct=cov, lint_clean=True,
        total_tests=100, tests_passed=int(pass_rate * 100),
        tests_failed=100 - int(pass_rate * 100), error_summary="",
    )


def _budget_target() -> MagicMock:
    target = MagicMock()
    target.name = "code"
    target.allowed_paths = ["src/"]
    target.max_diff_lines = 50
    target.get_editable_files = MagicMock(return_value=[])
    target.build_context = AsyncMock(return_value="context")
    target.invalidate_eval_cache = MagicMock()
    return target


class TestBudgetsAndSimplicity:
    @pytest.mark.asyncio
    async def test_hours_cap_stops_loop(self, tmp_path: Path) -> None:
        from silkroute.autoresearch.engine import ResearchEngine

        target = _budget_target()
        target.evaluate = AsyncMock(return_value=_metrics(0.8))

        engine = ResearchEngine(
            target=target, model_id="test-model", project_root=tmp_path,
            max_experiments=10, max_hours=1.0,
        )

        import silkroute.db.pool as pool_mod
        pool_mod._pool = None

        with patch.object(engine, "_create_branch", return_value="autoresearch/test"), \
             patch.object(engine, "_git_short_hash", return_value="abc1234"), \
             patch.object(engine, "_setup_signal_handlers"), \
             patch("silkroute.autoresearch.engine.time.monotonic",
                   side_effect=[0.0, 9_999_999.0]), \
             patch("silkroute.db.pool.asyncpg.create_pool",
                   new_callable=AsyncMock, side_effect=OSError("no db")):
            await engine.run()

        pool_mod._pool = None

        # Only the baseline row — the cap tripped before any experiment ran.
        entries = engine.ledger.read()
        assert len(entries) == 1
        assert entries[0].description == "baseline"

    @pytest.mark.asyncio
    async def test_experiment_timeout_records_crash(self, tmp_path: Path) -> None:
        from silkroute.autoresearch.engine import ResearchEngine

        target = _budget_target()

        # First evaluate() = baseline (fast); second = the hanging experiment.
        calls = {"n": 0}

        async def _evaluate() -> Metrics:
            calls["n"] += 1
            if calls["n"] == 1:
                return _metrics(0.8)
            await asyncio.sleep(5)
            return _metrics(0.9)

        target.evaluate = _evaluate

        engine = ResearchEngine(
            target=target, model_id="test-model", project_root=tmp_path,
            max_experiments=1, experiment_timeout_seconds=0.05,
        )

        import silkroute.db.pool as pool_mod
        pool_mod._pool = None

        with patch.object(engine, "_create_branch", return_value="autoresearch/test"), \
             patch.object(engine, "_git_short_hash", return_value="def5678"), \
             patch.object(engine, "_git_commit", return_value="def5678"), \
             patch.object(engine, "_git_reset") as mock_reset, \
             patch.object(engine, "_revert_if_dirty"), \
             patch.object(engine, "_setup_signal_handlers"), \
             patch("silkroute.autoresearch.engine.propose_change", new_callable=AsyncMock) as mock_propose, \
             patch.object(engine, "_validate_change"), \
             patch.object(engine, "_apply_change"), \
             patch("silkroute.db.pool.asyncpg.create_pool",
                   new_callable=AsyncMock, side_effect=OSError("no db")):
            mock_propose.return_value = ProposedChange(
                file_path="src/test.py", old_code="old", new_code="new", rationale="slow one",
            )
            await engine.run()

        pool_mod._pool = None

        entries = engine.ledger.read()
        crash = [e for e in entries if e.status == "crash"]
        assert len(crash) == 1
        assert "timeout" in crash[0].description
        # Pending commit rolled back: HEAD == pending hash → _git_reset called.
        mock_reset.assert_called_once()

    @pytest.mark.asyncio
    async def test_equal_score_smaller_diff_kept_as_simplify(self, tmp_path: Path) -> None:
        from silkroute.autoresearch.engine import ResearchEngine

        target = _budget_target()
        # Baseline and candidate score identically.
        target.evaluate = AsyncMock(side_effect=[_metrics(0.8), _metrics(0.8)])

        engine = ResearchEngine(
            target=target, model_id="test-model", project_root=tmp_path, max_experiments=1,
        )

        import silkroute.db.pool as pool_mod
        pool_mod._pool = None

        with patch.object(engine, "_create_branch", return_value="autoresearch/test"), \
             patch.object(engine, "_git_short_hash", return_value="def5678"), \
             patch.object(engine, "_git_commit", return_value="def5678"), \
             patch.object(engine, "_git_reset") as mock_reset, \
             patch.object(engine, "_setup_signal_handlers"), \
             patch("silkroute.autoresearch.engine.propose_change", new_callable=AsyncMock) as mock_propose, \
             patch.object(engine, "_validate_change"), \
             patch.object(engine, "_apply_change"), \
             patch("silkroute.db.pool.asyncpg.create_pool",
                   new_callable=AsyncMock, side_effect=OSError("no db")):
            mock_propose.return_value = ProposedChange(
                file_path="src/test.py",
                old_code="line1\nline2\nline3\n",
                new_code="line1\n",
                rationale="collapse three lines to one",
            )
            await engine.run()

        pool_mod._pool = None

        mock_reset.assert_not_called()
        entries = engine.ledger.read()
        assert entries[1].status == "keep"
        assert entries[1].description.startswith("simplify: ")

    @pytest.mark.asyncio
    async def test_equal_score_larger_diff_discarded(self, tmp_path: Path) -> None:
        from silkroute.autoresearch.engine import ResearchEngine

        target = _budget_target()
        target.evaluate = AsyncMock(side_effect=[_metrics(0.8), _metrics(0.8)])

        engine = ResearchEngine(
            target=target, model_id="test-model", project_root=tmp_path, max_experiments=1,
        )

        import silkroute.db.pool as pool_mod
        pool_mod._pool = None

        with patch.object(engine, "_create_branch", return_value="autoresearch/test"), \
             patch.object(engine, "_git_short_hash", return_value="def5678"), \
             patch.object(engine, "_git_commit", return_value="def5678"), \
             patch.object(engine, "_git_reset") as mock_reset, \
             patch.object(engine, "_setup_signal_handlers"), \
             patch("silkroute.autoresearch.engine.propose_change", new_callable=AsyncMock) as mock_propose, \
             patch.object(engine, "_validate_change"), \
             patch.object(engine, "_apply_change"), \
             patch("silkroute.db.pool.asyncpg.create_pool",
                   new_callable=AsyncMock, side_effect=OSError("no db")):
            mock_propose.return_value = ProposedChange(
                file_path="src/test.py",
                old_code="line1\n",
                new_code="line1\nline2\nline3\n",
                rationale="add complexity, same score",
            )
            await engine.run()

        pool_mod._pool = None

        mock_reset.assert_called_once()
        target.invalidate_eval_cache.assert_called()
        entries = engine.ledger.read()
        assert entries[1].status == "discard"


# ── Engine ↔ agent_memories bridge ───────────────────────────────────


class TestEngineMemoryBridge:
    def _target(self) -> MagicMock:
        target = MagicMock()
        target.name = "code"
        target.allowed_paths = ["src/"]
        target.max_diff_lines = 50
        target.get_editable_files = MagicMock(return_value=[])
        target.build_context = AsyncMock(return_value="context")
        return target

    @pytest.mark.asyncio
    async def test_keep_records_outcome_memory(self, tmp_path: Path) -> None:
        from silkroute.autoresearch.engine import ResearchEngine

        target = self._target()
        baseline = Metrics(
            pass_rate=0.8, coverage_pct=0.5, lint_clean=True,
            total_tests=100, tests_passed=80, tests_failed=20, error_summary="",
        )
        improved = Metrics(
            pass_rate=0.9, coverage_pct=0.6, lint_clean=True,
            total_tests=100, tests_passed=90, tests_failed=10, error_summary="",
        )
        target.evaluate = AsyncMock(side_effect=[baseline, improved])

        engine = ResearchEngine(
            target=target, model_id="test-model", project_root=tmp_path,
            max_experiments=1, project_id="proj-1",
        )

        import silkroute.db.pool as pool_mod
        pool_mod._pool = None
        mock_pool = AsyncMock()

        with patch.object(engine, "_create_branch", return_value="autoresearch/test"), \
             patch.object(engine, "_git_short_hash", return_value="abc1234"), \
             patch.object(engine, "_git_commit", return_value="def5678"), \
             patch.object(engine, "_git_reset") as mock_reset, \
             patch.object(engine, "_setup_signal_handlers"), \
             patch("silkroute.autoresearch.engine.propose_change", new_callable=AsyncMock) as mock_propose, \
             patch.object(engine, "_validate_change"), \
             patch.object(engine, "_apply_change"), \
             patch(
                 "silkroute.db.pool.asyncpg.create_pool",
                 new_callable=AsyncMock, return_value=mock_pool,
             ), \
             patch(
                 "silkroute.db.repositories.memories.insert_memory", new_callable=AsyncMock,
             ) as mock_insert:
            mock_propose.return_value = ProposedChange(
                file_path="src/test.py", old_code="old", new_code="new",
                rationale="improved something",
            )
            await engine.run()

        pool_mod._pool = None

        mock_reset.assert_not_called()
        mock_insert.assert_called_once()
        _, kwargs = mock_insert.call_args
        assert kwargs["kind"] == "outcome"
        assert kwargs["importance"] == 0.6
        assert kwargs["project_id"] == "proj-1"

    @pytest.mark.asyncio
    async def test_discard_records_outcome_memory(self, tmp_path: Path) -> None:
        from silkroute.autoresearch.engine import ResearchEngine

        target = self._target()
        baseline = Metrics(
            pass_rate=0.9, coverage_pct=0.8, lint_clean=True,
            total_tests=100, tests_passed=90, tests_failed=10, error_summary="",
        )
        worse = Metrics(
            pass_rate=0.7, coverage_pct=0.6, lint_clean=True,
            total_tests=100, tests_passed=70, tests_failed=30, error_summary="",
        )
        target.evaluate = AsyncMock(side_effect=[baseline, worse])

        engine = ResearchEngine(
            target=target, model_id="test-model", project_root=tmp_path, max_experiments=1,
        )

        import silkroute.db.pool as pool_mod
        pool_mod._pool = None
        mock_pool = AsyncMock()

        with patch.object(engine, "_create_branch", return_value="autoresearch/test"), \
             patch.object(engine, "_git_short_hash", return_value="abc1234"), \
             patch.object(engine, "_git_commit", return_value="def5678"), \
             patch.object(engine, "_git_reset") as mock_reset, \
             patch.object(engine, "_setup_signal_handlers"), \
             patch("silkroute.autoresearch.engine.propose_change", new_callable=AsyncMock) as mock_propose, \
             patch.object(engine, "_validate_change"), \
             patch.object(engine, "_apply_change"), \
             patch(
                 "silkroute.db.pool.asyncpg.create_pool",
                 new_callable=AsyncMock, return_value=mock_pool,
             ), \
             patch(
                 "silkroute.db.repositories.memories.insert_memory", new_callable=AsyncMock,
             ) as mock_insert:
            mock_propose.return_value = ProposedChange(
                file_path="src/test.py", old_code="old", new_code="new",
                rationale="broke something",
            )
            await engine.run()

        pool_mod._pool = None

        mock_reset.assert_called_once()
        mock_insert.assert_called_once()
        _, kwargs = mock_insert.call_args
        assert kwargs["importance"] == 0.3

    @pytest.mark.asyncio
    async def test_memory_failure_does_not_break_keep_flow(self, tmp_path: Path) -> None:
        from silkroute.autoresearch.engine import ResearchEngine

        target = self._target()
        baseline = Metrics(
            pass_rate=0.8, coverage_pct=0.5, lint_clean=True,
            total_tests=100, tests_passed=80, tests_failed=20, error_summary="",
        )
        improved = Metrics(
            pass_rate=0.9, coverage_pct=0.6, lint_clean=True,
            total_tests=100, tests_passed=90, tests_failed=10, error_summary="",
        )
        target.evaluate = AsyncMock(side_effect=[baseline, improved])

        engine = ResearchEngine(
            target=target, model_id="test-model", project_root=tmp_path, max_experiments=1,
        )

        import silkroute.db.pool as pool_mod
        pool_mod._pool = None
        mock_pool = AsyncMock()

        with patch.object(engine, "_create_branch", return_value="autoresearch/test"), \
             patch.object(engine, "_git_short_hash", return_value="abc1234"), \
             patch.object(engine, "_git_commit", return_value="def5678"), \
             patch.object(engine, "_git_reset") as mock_reset, \
             patch.object(engine, "_setup_signal_handlers"), \
             patch("silkroute.autoresearch.engine.propose_change", new_callable=AsyncMock) as mock_propose, \
             patch.object(engine, "_validate_change"), \
             patch.object(engine, "_apply_change"), \
             patch(
                 "silkroute.db.pool.asyncpg.create_pool",
                 new_callable=AsyncMock, return_value=mock_pool,
             ), \
             patch(
                 "silkroute.db.repositories.memories.insert_memory",
                 new_callable=AsyncMock, side_effect=RuntimeError("db down"),
             ):
            mock_propose.return_value = ProposedChange(
                file_path="src/test.py", old_code="old", new_code="new",
                rationale="improved something",
            )
            await engine.run()  # must not raise

        pool_mod._pool = None

        mock_reset.assert_not_called()
        entries = engine.ledger.read()
        assert len(entries) == 2
        assert entries[1].status == "keep"

    @pytest.mark.asyncio
    async def test_fail_open_no_pool_available(self, tmp_path: Path) -> None:
        from silkroute.autoresearch.engine import ResearchEngine

        target = self._target()
        baseline = Metrics(
            pass_rate=0.8, coverage_pct=0.5, lint_clean=True,
            total_tests=100, tests_passed=80, tests_failed=20, error_summary="",
        )
        improved = Metrics(
            pass_rate=0.9, coverage_pct=0.6, lint_clean=True,
            total_tests=100, tests_passed=90, tests_failed=10, error_summary="",
        )
        target.evaluate = AsyncMock(side_effect=[baseline, improved])

        engine = ResearchEngine(
            target=target, model_id="test-model", project_root=tmp_path, max_experiments=1,
        )

        import silkroute.db.pool as pool_mod
        pool_mod._pool = None

        with patch.object(engine, "_create_branch", return_value="autoresearch/test"), \
             patch.object(engine, "_git_short_hash", return_value="abc1234"), \
             patch.object(engine, "_git_commit", return_value="def5678"), \
             patch.object(engine, "_git_reset") as mock_reset, \
             patch.object(engine, "_setup_signal_handlers"), \
             patch("silkroute.autoresearch.engine.propose_change", new_callable=AsyncMock) as mock_propose, \
             patch.object(engine, "_validate_change"), \
             patch.object(engine, "_apply_change"), \
             patch(
                 "silkroute.db.pool.asyncpg.create_pool",
                 new_callable=AsyncMock, side_effect=OSError("refused"),
             ), \
             patch(
                 "silkroute.db.repositories.memories.insert_memory", new_callable=AsyncMock,
             ) as mock_insert:
            mock_propose.return_value = ProposedChange(
                file_path="src/test.py", old_code="old", new_code="new",
                rationale="improved something",
            )
            await engine.run()

        pool_mod._pool = None

        mock_insert.assert_not_called()
        mock_reset.assert_not_called()
        entries = engine.ledger.read()
        assert len(entries) == 2


class TestCodeImproverTargetMemory:
    @pytest.mark.asyncio
    async def test_memory_section_included_when_available(self, tmp_path: Path) -> None:
        from silkroute.autoresearch.targets.code import CodeImproverTarget

        target = CodeImproverTarget(tmp_path, project_id="proj-1")

        import silkroute.db.pool as pool_mod
        pool_mod._pool = None
        mock_pool = AsyncMock()

        with patch.object(target, "_get_test_summary", new=AsyncMock(return_value="all pass")), \
             patch.object(target, "_get_coverage_gaps", new=AsyncMock(return_value="")), \
             patch(
                 "silkroute.db.pool.asyncpg.create_pool",
                 new_callable=AsyncMock, return_value=mock_pool,
             ), \
             patch(
                 "silkroute.db.repositories.memories.recall_memories",
                 new_callable=AsyncMock,
                 return_value=[{"kind": "outcome", "content": "keep: improved something (score 0.9)"}],
             ):
            context = await target.build_context([])

        pool_mod._pool = None

        assert "## Relevant Past Learnings" in context
        assert "improved something" in context

    @pytest.mark.asyncio
    async def test_memory_section_absent_when_pool_unavailable(self, tmp_path: Path) -> None:
        from silkroute.autoresearch.targets.code import CodeImproverTarget

        target = CodeImproverTarget(tmp_path)

        import silkroute.db.pool as pool_mod
        pool_mod._pool = None

        with patch.object(target, "_get_test_summary", new=AsyncMock(return_value="all pass")), \
             patch.object(target, "_get_coverage_gaps", new=AsyncMock(return_value="")), \
             patch(
                 "silkroute.db.pool.asyncpg.create_pool",
                 new_callable=AsyncMock, side_effect=OSError("refused"),
             ):
            context = await target.build_context([])

        pool_mod._pool = None

        assert "## Relevant Past Learnings" not in context
        assert "## Current Test Status" in context

    @pytest.mark.asyncio
    async def test_memory_section_absent_when_recall_raises(self, tmp_path: Path) -> None:
        from silkroute.autoresearch.targets.code import CodeImproverTarget

        target = CodeImproverTarget(tmp_path)

        import silkroute.db.pool as pool_mod
        pool_mod._pool = None
        mock_pool = AsyncMock()

        with patch.object(target, "_get_test_summary", new=AsyncMock(return_value="all pass")), \
             patch.object(target, "_get_coverage_gaps", new=AsyncMock(return_value="")), \
             patch(
                 "silkroute.db.pool.asyncpg.create_pool",
                 new_callable=AsyncMock, return_value=mock_pool,
             ), \
             patch(
                 "silkroute.db.repositories.memories.recall_memories",
                 new_callable=AsyncMock, side_effect=RuntimeError("db down"),
             ):
            context = await target.build_context([])

        pool_mod._pool = None

        assert "## Relevant Past Learnings" not in context
        assert "## Current Test Status" in context


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
