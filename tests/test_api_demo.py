"""Tests for the /demo AV/edge endpoints (room state + SSE agent trace)."""

from __future__ import annotations

import json
import os
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from fastapi.testclient import TestClient

import silkroute.api.routes.demo as demo_module
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

    def test_stream_live_false_is_unchanged(self, app: TestClient) -> None:
        """Explicit ?live=false must be byte-for-byte the same scripted replay."""
        resp = app.get("/demo/stream?delay=0&live=false")
        frames = [
            json.loads(line[len("data: ") :])
            for line in resp.text.splitlines()
            if line.startswith("data: ") and not line.startswith("data: [")
        ]
        types = [f["type"] for f in frames]
        assert types == [
            "session_start", "thought", "tool_call", "thought", "answer", "session_complete",
        ]


def _mock_completion(content: str, tool_calls=None):
    """Build a mock litellm completion response (mirrors tests/test_loop.py)."""
    message = MagicMock()
    message.content = content
    message.tool_calls = tool_calls
    message.model_dump.return_value = {"role": "assistant", "content": content, "tool_calls": None}
    choice = MagicMock()
    choice.message = message
    response = MagicMock()
    response.choices = [choice]
    usage = MagicMock()
    usage.prompt_tokens = 100
    usage.completion_tokens = 50
    response.usage = usage
    return response


def _mock_tool_call(tool_name: str, arguments: str):
    """Build a mock litellm response containing one tool call."""
    tc = MagicMock()
    tc.id = "call_test_123"
    tc.function = MagicMock()
    tc.function.name = tool_name
    tc.function.arguments = arguments
    message = MagicMock()
    message.content = "Let me check that."
    message.tool_calls = [tc]
    message.model_dump.return_value = {
        "role": "assistant",
        "content": "Let me check that.",
        "tool_calls": [{"id": "call_test_123", "function": {"name": tool_name, "arguments": arguments}}],
    }
    choice = MagicMock()
    choice.message = message
    response = MagicMock()
    response.choices = [choice]
    usage = MagicMock()
    usage.prompt_tokens = 150
    usage.completion_tokens = 80
    response.usage = usage
    return response


_MOCK_MCP_ENV_KEYS = (
    "SILKROUTE_MCP_EPIPHAN_ENABLED",
    "SILKROUTE_MCP_EPIPHAN_COMMAND",
    "SILKROUTE_MCP_EPIPHAN_ARGS",
)


@pytest.fixture(autouse=True)
def _isolate_mock_mcp_env(monkeypatch: pytest.MonkeyPatch):
    """Keep _ensure_mock_mcp_env's os.environ.setdefault calls from leaking.

    monkeypatch.delenv only reverts changes made *through* monkeypatch — it
    can't know to undo the production code's own os.environ.setdefault(...)
    calls during the test, so those must be cleaned up explicitly afterward.
    """
    monkeypatch.setattr(demo_module, "_mock_mcp_env_ready", False)
    for key in _MOCK_MCP_ENV_KEYS:
        monkeypatch.delenv(key, raising=False)
    yield
    for key in _MOCK_MCP_ENV_KEYS:
        os.environ.pop(key, None)


class TestDemoStreamLive:
    """GET /demo/stream?live=true — a real run_agent() loop, LLM mocked."""

    @pytest.fixture(autouse=True)
    def _disable_db_persistence(self):
        with patch("silkroute.agent.loop.AgentConfig") as mock_cfg:
            mock_cfg.return_value.persist_sessions = False
            yield

    def _frames(self, text: str) -> list[dict]:
        return [
            json.loads(line[len("data: ") :])
            for line in text.splitlines()
            if line.startswith("data: ") and not line.startswith("data: [")
        ]

    def test_live_happy_path(self, app: TestClient) -> None:
        tool_response = _mock_tool_call("get_recording_status", "{}")
        final_response = _mock_completion("Yes, recording is active.")

        with patch("silkroute.agent.loop.litellm") as mock_litellm:
            mock_litellm.acompletion = AsyncMock(side_effect=[tool_response, final_response])
            mock_litellm.completion_cost.return_value = 0.0001
            mock_litellm.suppress_debug_info = True

            resp = app.get("/demo/stream?live=true&delay=0")

        assert resp.status_code == 200
        frames = self._frames(resp.text)
        types = [f["type"] for f in frames]
        assert types == ["session_start", "thought", "tool_call", "answer", "session_complete"]

        assert frames[0]["data"]["live"] is True
        tool_frame = next(f for f in frames if f["type"] == "tool_call")
        assert tool_frame["data"]["count"] == 1
        answer = next(f for f in frames if f["type"] == "answer")
        assert answer["data"]["text"] == "Yes, recording is active."
        complete = frames[-1]
        assert complete["data"]["live"] is True
        assert complete["data"]["iterations"] == 2
        assert resp.text.rstrip().endswith("[DONE]")

    def test_live_inconclusive_still_yields_an_answer(self, app: TestClient) -> None:
        """Model keeps calling tools and never converges within max_iterations."""
        tool_response = _mock_tool_call("get_recording_status", "{}")

        with patch("silkroute.agent.loop.litellm") as mock_litellm:
            mock_litellm.acompletion = AsyncMock(return_value=tool_response)
            mock_litellm.completion_cost.return_value = 0.0001
            mock_litellm.suppress_debug_info = True

            resp = app.get("/demo/stream?live=true&delay=0")

        assert resp.status_code == 200
        frames = self._frames(resp.text)
        types = [f["type"] for f in frames]
        # session_start, then 4x (thought, tool_call), then a synthesized answer + session_complete
        assert types.count("tool_call") == 4
        assert types[-2:] == ["answer", "session_complete"]
        assert "step limit" in frames[-2]["data"]["text"]
        assert frames[-1]["data"]["inconclusive"] is True
        assert resp.text.rstrip().endswith("[DONE]")

    def test_live_llm_error_ends_stream_with_error_sentinel(self, app: TestClient) -> None:
        with patch("silkroute.agent.loop.litellm") as mock_litellm:
            mock_litellm.acompletion = AsyncMock(side_effect=RuntimeError("model unreachable"))
            mock_litellm.suppress_debug_info = True

            resp = app.get("/demo/stream?live=true&delay=0")

        assert resp.status_code == 200
        assert "[ERROR]" in resp.text
        assert "[DONE]" not in resp.text


class TestLiveDemoConcurrencyGuard:
    """_LIVE_DEMO_SEMAPHORE — caps concurrent live-mode streams.

    Drives _stream_live_trace directly (not via TestClient) so the whole test
    runs on a single event loop — acquiring/timing-out on the real semaphore
    across TestClient's per-call loop would risk asyncio's cross-loop binding
    gotchas for no benefit here.
    """

    @pytest.mark.asyncio
    async def test_yields_busy_when_semaphore_exhausted(self) -> None:
        await demo_module._LIVE_DEMO_SEMAPHORE.acquire()
        await demo_module._LIVE_DEMO_SEMAPHORE.acquire()
        try:
            frames = [
                chunk
                async for chunk in demo_module._stream_live_trace(
                    "test task", "ollama/qwen2.5:14b",
                )
            ]
        finally:
            demo_module._LIVE_DEMO_SEMAPHORE.release()
            demo_module._LIVE_DEMO_SEMAPHORE.release()

        assert len(frames) == 1
        assert "server busy" in frames[0]


class TestEnsureMockMcpEnv:
    """_ensure_mock_mcp_env — one-time, setdefault-based env setup.

    Isolated from other tests by the module-level `_isolate_mock_mcp_env`
    autouse fixture above.
    """

    def test_setdefault_leaves_existing_config_untouched(
        self, monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        monkeypatch.setenv("SILKROUTE_MCP_EPIPHAN_COMMAND", "/usr/bin/real-epiphan-bridge")

        demo_module._ensure_mock_mcp_env()

        assert os.environ["SILKROUTE_MCP_EPIPHAN_COMMAND"] == "/usr/bin/real-epiphan-bridge"
        assert demo_module._mock_mcp_env_ready is True

    def test_sets_all_three_vars_when_absent(self) -> None:
        demo_module._ensure_mock_mcp_env()

        assert os.environ["SILKROUTE_MCP_EPIPHAN_ENABLED"] == "true"
        assert "mock_epiphan_mcp.py" in os.environ["SILKROUTE_MCP_EPIPHAN_ARGS"]


class TestDemoHeal:
    """GET /demo/heal (self-healing loop over SSE)."""

    def _frames(self, text: str) -> list[dict]:
        return [
            json.loads(line[len("data: ") :])
            for line in text.splitlines()
            if line.startswith("data: ") and not line.startswith("data: [")
        ]

    def test_heal_streams_detect_fix_verify(self, app: TestClient) -> None:
        # signal_loss is handled by the seed playbook → should heal.
        resp = app.get("/demo/heal?fault=signal_loss&delay=0")
        assert resp.status_code == 200
        assert resp.headers["content-type"].startswith("text/event-stream")
        frames = self._frames(resp.text)
        types = [f["type"] for f in frames]
        assert types[0] == "heal_start"
        assert "heal_step" in types
        result = next(f for f in frames if f["type"] == "heal_result")
        assert result["data"]["fault_type"] == "signal_loss"
        assert result["data"]["action"] == "restart_input"
        assert result["data"]["verified"] is True
        assert result["data"]["outcome"] == "healed"
        assert resp.text.rstrip().endswith("[DONE]")

    def test_heal_reports_unhandled_fault(
        self, app: TestClient, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        # The LIVE playbook now heals every fault (PR #1), so pin the "detected,
        # not fixed" reporting path against the frozen seed fixture, which has
        # no cpu_overload rule.
        import silkroute.autoresearch.heal as heal_module

        seed = Path(__file__).resolve().parent / "fixtures" / "seed_remediation_rules.yaml"
        real_heal_with_mock = heal_module.heal_with_mock

        async def _heal_with_seed(fault: str, **kwargs: object) -> object:
            kwargs["playbook_path"] = seed
            return await real_heal_with_mock(fault, **kwargs)  # type: ignore[arg-type]

        monkeypatch.setattr(heal_module, "heal_with_mock", _heal_with_seed)
        resp = app.get("/demo/heal?fault=cpu_overload&delay=0")
        frames = self._frames(resp.text)
        result = next(f for f in frames if f["type"] == "heal_result")
        assert result["data"]["fault_type"] == "cpu_overload"
        assert result["data"]["outcome"] == "unhandled"
        assert result["data"]["verified"] is False

    def test_heal_rejects_unknown_fault(self, app: TestClient) -> None:
        # Unknown fault falls back to the default (signal_loss) — still valid stream.
        resp = app.get("/demo/heal?fault=nonsense&delay=0")
        assert resp.status_code == 200
        frames = self._frames(resp.text)
        result = next(f for f in frames if f["type"] == "heal_result")
        assert result["data"]["fault_type"] == "signal_loss"
