"""Tests for the /demo AV/edge endpoints (room state + SSE agent trace)."""

from __future__ import annotations

import json

import pytest
from fastapi.testclient import TestClient

from silkroute.api.app import create_app
from silkroute.config.settings import SilkRouteSettings


@pytest.fixture
def app(test_settings: SilkRouteSettings) -> TestClient:
    # Demo endpoints have no auth / redis / db dependencies.
    application = create_app(settings=test_settings)
    application.state.db_pool = None
    return TestClient(application, raise_server_exceptions=False)


class TestDemoRoom:
    """GET /demo/room."""

    def test_room_returns_shaped_state(self, app: TestClient) -> None:
        resp = app.get("/demo/room")
        assert resp.status_code == 200
        body = resp.json()
        assert body["device_name"] == "Pearl-2-Room320B"
        assert body["recorder_state"] == "recording"
        assert body["healthy"] is True
        assert body["duration_seconds"] == 1800
        # In the test env the repo-root demo/ package is importable.
        assert body["source"] == "mock"

    def test_room_is_ungated(self, app: TestClient) -> None:
        # No Authorization header — public demo endpoint must still answer 200.
        assert app.get("/demo/room").status_code == 200


class TestDemoStream:
    """GET /demo/stream (Server-Sent Events)."""

    def test_stream_emits_full_trace(self, app: TestClient) -> None:
        resp = app.get("/demo/stream?delay=0")
        assert resp.status_code == 200
        assert resp.headers["content-type"].startswith("text/event-stream")

        frames = [
            json.loads(line[len("data: ") :])
            for line in resp.text.splitlines()
            if line.startswith("data: ") and not line.startswith("data: [")
        ]
        types = [f["type"] for f in frames]
        assert types[0] == "session_start"
        assert "tool_call" in types
        assert types[-1] == "session_complete"

        tool_frame = next(f for f in frames if f["type"] == "tool_call")
        assert tool_frame["data"]["tool_name"] == "get_recording_status"
        assert tool_frame["data"]["success"] is True

        answer = next(f for f in frames if f["type"] == "answer")
        assert "Yes" in answer["data"]["text"]  # recorder is recording in the mock

        assert resp.text.rstrip().endswith("[DONE]")

    def test_stream_accepts_custom_task(self, app: TestClient) -> None:
        resp = app.get("/demo/stream?delay=0&task=is+the+room+recording")
        assert resp.status_code == 200
        assert "is the room recording" in resp.text
