"""Shared test fixtures for daemon tests."""

from __future__ import annotations

import pytest
import fakeredis.aioredis


@pytest.fixture
async def fake_redis() -> fakeredis.aioredis.FakeRedis:
    """Provide a fresh fakeredis async client for each test."""
    client = fakeredis.aioredis.FakeRedis(decode_responses=True)
    yield client
    await client.aclose()
