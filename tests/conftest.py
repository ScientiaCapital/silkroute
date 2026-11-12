"""Shared test fixtures for daemon and API tests."""

from __future__ import annotations

import os

# LiteLLM downloads its model price list from GitHub on import unless told to use the
# bundled copy. Set it before anything imports litellm so the suite stays offline.
os.environ.setdefault("LITELLM_LOCAL_MODEL_COST_MAP", "True")

import fakeredis.aioredis  # noqa: E402
import pytest

from silkroute.config.settings import (
    ApiConfig,
    DatabaseConfig,
    ProviderConfig,
    SilkRouteSettings,
)

_FAKE_PUBLIC_IP = "93.184.216.34"


@pytest.fixture(autouse=True)
def _no_real_dns(monkeypatch: pytest.MonkeyPatch) -> None:
    """Keep the SSRF guard's DNS lookups off the network.

    The guard fails closed when resolution fails, so tests that use public
    hostnames (example.com, httpbin.org) need a deterministic resolver. Every
    hostname resolves to a fixed public address (93.184.216.34) unless a test
    patches ``silkroute.network.ssrf._getaddrinfo`` itself (only the
    guard's alias is replaced, never the process-wide ``socket`` module).
    """
    import socket

    def fake_getaddrinfo(host, port, *args, **kwargs):  # noqa: ANN001, ANN002, ANN003, ANN202
        return [(socket.AF_INET, socket.SOCK_STREAM, 6, "", (_FAKE_PUBLIC_IP, port or 0))]

    monkeypatch.setattr("silkroute.network.ssrf._getaddrinfo", fake_getaddrinfo)


@pytest.fixture(autouse=True)
def _reset_tool_sandbox(monkeypatch: pytest.MonkeyPatch) -> None:
    """create_default_registry() sets a module-global sandbox; isolate tests."""
    monkeypatch.setattr("silkroute.agent.tools._sandbox_config", None)


@pytest.fixture
async def fake_redis() -> fakeredis.aioredis.FakeRedis:
    """Provide a fresh fakeredis async client for each test."""
    client = fakeredis.aioredis.FakeRedis(decode_responses=True)
    yield client
    await client.aclose()


@pytest.fixture
def test_settings() -> SilkRouteSettings:
    """Shared SilkRouteSettings for API tests (Ollama enabled, test API key)."""
    return SilkRouteSettings(
        providers=ProviderConfig(ollama_enabled=True),
        api=ApiConfig(api_key="test-secret"),
        database=DatabaseConfig(
            redis_url="redis://localhost:6379/0",
            postgres_url="postgresql://silkroute:silkroute@localhost:5432/silkroute",
        ),
    )
