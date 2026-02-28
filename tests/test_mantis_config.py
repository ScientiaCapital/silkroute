"""Tests for MantisConfig (config/settings.py)."""

from __future__ import annotations

import pytest

from silkroute.config.settings import MantisConfig, SilkRouteSettings


class TestMantisConfig:
    """MantisConfig defaults and env var overrides."""

    def test_defaults(self) -> None:
        config = MantisConfig()
        assert config.runtime == "legacy"
        assert config.default_model == "deepseek/deepseek-v3.2"
        assert config.code_writer_model == "qwen/qwen3-coder"
        assert config.max_iterations == 50
        assert config.budget_limit_usd == 5.0
        assert config.default_backend == "local_shell"
        assert config.enable_subagents is False

    def test_env_var_override(self, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.setenv("SILKROUTE_MANTIS_RUNTIME", "deepagents")
        monkeypatch.setenv("SILKROUTE_MANTIS_MAX_ITERATIONS", "100")
        config = MantisConfig()
        assert config.runtime == "deepagents"
        assert config.max_iterations == 100

    def test_default_backend_is_local_shell(self) -> None:
        config = MantisConfig()
        assert config.default_backend == "local_shell"

    def test_settings_includes_mantis(self, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.setenv("SILKROUTE_OPENROUTER_API_KEY", "sk-test")
        settings = SilkRouteSettings()
        assert hasattr(settings, "mantis")
        assert isinstance(settings.mantis, MantisConfig)
        assert settings.mantis.runtime == "legacy"
