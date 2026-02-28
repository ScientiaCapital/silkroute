"""Shared test fixtures for daemon and API tests."""

from __future__ import annotations

import fakeredis.aioredis
import pytest

from silkroute.config.settings import (
    ApiConfig,
    DatabaseConfig,
    ProviderConfig,
    SilkRouteSettings,
)


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
