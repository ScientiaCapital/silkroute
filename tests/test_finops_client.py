"""Tests for silkroute.integrations.finops_client — fail-open behavior."""

from unittest.mock import AsyncMock, MagicMock, patch

import httpx

from silkroute.config.settings import FinopsConfig
from silkroute.integrations.finops_client import report_usage

USAGE_KWARGS = {
    "provider": "ollama",
    "model": "ollama/qwen2.5:14b",
    "input_tokens": 100,
    "output_tokens": 40,
    "cost_usd": 0.0,
    "task_type": "did recording start in room 320-B",
    "session_id": "sess-1",
    "project_id": "av-demo",
    "latency_ms": 500,
}


def _mock_async_client(
    post_result_or_side_effect: object, *, is_side_effect: bool = False
) -> tuple[MagicMock, MagicMock]:
    """Patch httpx.AsyncClient so `async with httpx.AsyncClient(...) as client` works."""
    mock_client = MagicMock(spec=httpx.AsyncClient)
    if is_side_effect:
        mock_client.post = AsyncMock(side_effect=post_result_or_side_effect)
    else:
        mock_client.post = AsyncMock(return_value=post_result_or_side_effect)
    mock_context = MagicMock()
    mock_context.__aenter__ = AsyncMock(return_value=mock_client)
    mock_context.__aexit__ = AsyncMock(return_value=False)
    return mock_context, mock_client


def _make_response(status_code: int = 200) -> MagicMock:
    resp = MagicMock(spec=httpx.Response)
    resp.status_code = status_code
    if status_code >= 400:
        resp.raise_for_status.side_effect = httpx.HTTPStatusError(
            "error", request=MagicMock(), response=resp
        )
    else:
        resp.raise_for_status = MagicMock()
    return resp


class TestReportUsage:
    async def test_disabled_is_a_noop(self) -> None:
        cfg = FinopsConfig(enabled=False, base_url="http://localhost:8000", token="x")
        with patch("httpx.AsyncClient") as mock_cls:
            await report_usage(cfg, **USAGE_KWARGS)
        mock_cls.assert_not_called()

    async def test_enabled_posts_expected_payload(self) -> None:
        cfg = FinopsConfig(enabled=True, base_url="http://localhost:8000", token="secret")
        mock_context, mock_client = _mock_async_client(_make_response(200))
        with patch("httpx.AsyncClient", return_value=mock_context):
            await report_usage(cfg, **USAGE_KWARGS)

        mock_client.post.assert_awaited_once()
        _, kwargs = mock_client.post.call_args
        assert kwargs["headers"]["Authorization"] == "Bearer secret"
        assert kwargs["json"]["provider"] == "ollama"
        assert kwargs["json"]["model"] == "ollama/qwen2.5:14b"
        assert kwargs["json"]["source"] == "silkroute"

    async def test_http_error_is_swallowed(self) -> None:
        cfg = FinopsConfig(enabled=True, base_url="http://localhost:8000", token="x")
        mock_context, _ = _mock_async_client(_make_response(500))
        with patch("httpx.AsyncClient", return_value=mock_context):
            await report_usage(cfg, **USAGE_KWARGS)  # must not raise

    async def test_request_error_is_swallowed(self) -> None:
        cfg = FinopsConfig(enabled=True, base_url="http://localhost:8000", token="x")
        mock_context, _ = _mock_async_client(
            httpx.ConnectError("connection refused"), is_side_effect=True
        )
        with patch("httpx.AsyncClient", return_value=mock_context):
            await report_usage(cfg, **USAGE_KWARGS)  # must not raise

    async def test_unexpected_exception_is_swallowed(self) -> None:
        cfg = FinopsConfig(enabled=True, base_url="http://localhost:8000", token="x")
        mock_context, _ = _mock_async_client(
            ValueError("something unexpected"), is_side_effect=True
        )
        with patch("httpx.AsyncClient", return_value=mock_context):
            await report_usage(cfg, **USAGE_KWARGS)  # must not raise


class TestFinopsConfigDefaults:
    def test_defaults(self) -> None:
        cfg = FinopsConfig()
        assert cfg.enabled is False
        assert cfg.base_url == "http://localhost:8000"
        assert cfg.token == ""
        assert cfg.timeout_seconds == 3.0
