"""Tests for SupervisorConfig in config/settings.py."""

from __future__ import annotations

from silkroute.config.settings import ProviderConfig, SilkRouteSettings, SupervisorConfig


class TestSupervisorConfig:
    """SupervisorConfig defaults and env override."""

    def test_defaults(self):
        config = SupervisorConfig()
        assert config.enabled is False
        assert config.max_steps == 20
        assert config.step_timeout_seconds == 300
        assert config.session_timeout_seconds == 3600
        assert config.checkpoint_enabled is True
        assert config.max_retries == 2
        assert config.retry_backoff_seconds == 5.0
        assert config.ralph_cron == "*/30 * * * *"
        assert config.ralph_budget_usd == 5.0

    def test_env_override(self, monkeypatch):
        monkeypatch.setenv("SILKROUTE_SUPERVISOR_ENABLED", "true")
        monkeypatch.setenv("SILKROUTE_SUPERVISOR_MAX_STEPS", "50")
        monkeypatch.setenv("SILKROUTE_SUPERVISOR_RALPH_BUDGET_USD", "10.0")
        config = SupervisorConfig()
        assert config.enabled is True
        assert config.max_steps == 50
        assert config.ralph_budget_usd == 10.0

    def test_wired_into_root_settings(self):
        settings = SilkRouteSettings(
            providers=ProviderConfig(ollama_enabled=True),
        )
        assert isinstance(settings.supervisor, SupervisorConfig)
        assert settings.supervisor.enabled is False
