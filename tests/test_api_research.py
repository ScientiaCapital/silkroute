"""Tests for /research/ledger API route."""

from __future__ import annotations

from pathlib import Path

import fakeredis.aioredis
import pytest
from fastapi.testclient import TestClient

from silkroute.api.app import create_app
from silkroute.autoresearch.ledger import Ledger, LedgerEntry
from silkroute.config.settings import SilkRouteSettings
from silkroute.daemon.queue import TaskQueue


@pytest.fixture
def fake_redis_client() -> fakeredis.aioredis.FakeRedis:
    return fakeredis.aioredis.FakeRedis(decode_responses=True)


@pytest.fixture
def app(
    test_settings: SilkRouteSettings,
    fake_redis_client: fakeredis.aioredis.FakeRedis,
) -> TestClient:
    application = create_app(settings=test_settings)
    application.state.redis = fake_redis_client
    application.state.queue = TaskQueue(fake_redis_client, maxsize=100)
    application.state.db_pool = None
    return TestClient(application, raise_server_exceptions=False)


AUTH = {"Authorization": "Bearer test-secret"}


class TestGetLedgerRoute:
    def test_returns_available_false_when_no_ledger_file(
        self, app: TestClient, tmp_path: Path, monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        monkeypatch.chdir(tmp_path)
        response = app.get("/research/ledger", headers=AUTH)
        assert response.status_code == 200
        assert response.json() == {
            "entries": [], "counts": {}, "best": None, "available": False,
        }

    def test_returns_entries_counts_and_best(
        self, app: TestClient, tmp_path: Path, monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        monkeypatch.chdir(tmp_path)
        ledger = Ledger(tmp_path / ".silkroute" / "autoresearch" / "results.tsv")
        ledger.append(LedgerEntry("abc1234", 0.9, 1.0, 0.8, "keep", "improved routing"))
        ledger.append(LedgerEntry("def5678", 0.1, 0.5, 0.2, "discard", "bad idea"))

        response = app.get("/research/ledger", headers=AUTH)
        assert response.status_code == 200
        body = response.json()
        assert body["available"] is True
        assert len(body["entries"]) == 2
        assert body["counts"] == {"keep": 1, "discard": 1, "crash": 0, "total": 2}
        assert body["best"]["commit"] == "abc1234"
        assert body["best"]["score"] == pytest.approx(0.9)

    def test_requires_auth(self, app: TestClient) -> None:
        response = app.get("/research/ledger")
        assert response.status_code == 401
