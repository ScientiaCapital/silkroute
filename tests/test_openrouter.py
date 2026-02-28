"""Tests for the OpenRouter adapter (providers/openrouter.py)."""

from __future__ import annotations

import pytest

from silkroute.providers.openrouter import (
    _DEFAULT_HEADERS,
    _OPENROUTER_BASE_URL,
    _resolve_api_key,
    create_openrouter_model,
)


class TestCreateOpenrouterModel:
    """create_openrouter_model() creates a ChatOpenAI with OpenRouter config."""

    def test_creates_with_correct_base_url(self) -> None:
        model = create_openrouter_model(api_key="sk-test-123")
        assert str(model.openai_api_base) == _OPENROUTER_BASE_URL

    def test_model_id_passed_through(self) -> None:
        model = create_openrouter_model(
            model_id="qwen/qwen3-coder", api_key="sk-test-123"
        )
        assert model.model_name == "qwen/qwen3-coder"

    def test_temperature_default_zero(self) -> None:
        model = create_openrouter_model(api_key="sk-test-123")
        assert model.temperature == 0.0

    def test_temperature_override(self) -> None:
        model = create_openrouter_model(api_key="sk-test-123", temperature=0.7)
        assert model.temperature == 0.7

    def test_max_tokens_default(self) -> None:
        model = create_openrouter_model(api_key="sk-test-123")
        assert model.max_tokens == 4096

    def test_default_headers_set(self) -> None:
        model = create_openrouter_model(api_key="sk-test-123")
        headers = model.default_headers
        assert headers["HTTP-Referer"] == _DEFAULT_HEADERS["HTTP-Referer"]
        assert headers["X-Title"] == _DEFAULT_HEADERS["X-Title"]

    def test_extra_headers_merged(self) -> None:
        model = create_openrouter_model(
            api_key="sk-test-123",
            extra_headers={"X-Custom": "value"},
        )
        headers = model.default_headers
        assert headers["X-Custom"] == "value"
        assert headers["HTTP-Referer"] == _DEFAULT_HEADERS["HTTP-Referer"]

    def test_explicit_api_key_used(self) -> None:
        model = create_openrouter_model(api_key="sk-explicit-key")
        assert model.openai_api_key.get_secret_value() == "sk-explicit-key"


class TestResolveApiKey:
    """_resolve_api_key() fallback chain."""

    def test_raises_without_any_key(self, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.delenv("MANTIS_OPENROUTER_API_KEY", raising=False)
        monkeypatch.delenv("SILKROUTE_OPENROUTER_API_KEY", raising=False)
        with pytest.raises(ValueError, match="No OpenRouter API key found"):
            _resolve_api_key()

    def test_mantis_key_takes_precedence(self, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.setenv("MANTIS_OPENROUTER_API_KEY", "mantis-key")
        monkeypatch.setenv("SILKROUTE_OPENROUTER_API_KEY", "silkroute-key")
        assert _resolve_api_key() == "mantis-key"

    def test_falls_back_to_silkroute_key(self, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.delenv("MANTIS_OPENROUTER_API_KEY", raising=False)
        monkeypatch.setenv("SILKROUTE_OPENROUTER_API_KEY", "silkroute-key")
        assert _resolve_api_key() == "silkroute-key"
