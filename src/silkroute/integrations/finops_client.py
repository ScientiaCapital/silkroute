"""Fire-and-forget usage reporting to model-finops's telemetry ingest endpoint.

Fail-open, mirroring mantis/skills/context7.py's client pattern: any network
or API error is logged and swallowed, never raised — a reporting failure must
never break the agent loop that's actually doing the work.
"""

from __future__ import annotations

import httpx
import structlog

from silkroute.config.settings import FinopsConfig

log = structlog.get_logger()


async def report_usage(
    cfg: FinopsConfig,
    *,
    provider: str,
    model: str,
    input_tokens: int,
    output_tokens: int,
    cost_usd: float,
    task_type: str,
    session_id: str,
    project_id: str,
    latency_ms: int,
) -> None:
    """POST a completed iteration's usage to model-finops for dashboard tracking.

    No-op if reporting is disabled. Never raises — failures are logged and
    swallowed so a finops outage can't affect the agent loop.
    """
    if not cfg.enabled:
        return

    payload = {
        "provider": provider,
        "model": model,
        "input_tokens": input_tokens,
        "output_tokens": output_tokens,
        "cost_usd": cost_usd,
        "task_type": task_type,
        "session_id": session_id,
        "project_id": project_id,
        "latency_ms": latency_ms,
        "source": "silkroute",
    }

    try:
        async with httpx.AsyncClient(timeout=cfg.timeout_seconds) as client:
            response = await client.post(
                f"{cfg.base_url.rstrip('/')}/api/telemetry/ingest",
                headers={"Authorization": f"Bearer {cfg.token}"},
                json=payload,
            )
            response.raise_for_status()
    except httpx.HTTPStatusError as e:
        log.warning(
            "finops_report_http_error",
            status=e.response.status_code,
            model=model,
        )
    except httpx.RequestError as e:
        log.warning("finops_report_request_error", error=str(e), model=model)
    except Exception as e:
        log.warning("finops_report_error", error=str(e), model=model, exc_info=True)
