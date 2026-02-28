"""Runtime endpoints — direct invoke and SSE streaming.

POST /runtime/invoke → Synchronous runtime invocation
GET  /runtime/stream  → Server-Sent Events streaming
"""

from __future__ import annotations

import asyncio
from collections.abc import AsyncIterator

from fastapi import APIRouter, Depends, HTTPException, Query
from fastapi.responses import StreamingResponse

from silkroute.api.auth import require_auth
from silkroute.api.deps import get_api_config
from silkroute.api.models import RuntimeInvokeRequest, RuntimeInvokeResponse
from silkroute.config.settings import ApiConfig
from silkroute.mantis.runtime.interface import RuntimeConfig
from silkroute.mantis.runtime.registry import get_runtime

router = APIRouter(prefix="/runtime", tags=["runtime"], dependencies=[Depends(require_auth)])


@router.post("/invoke")
async def runtime_invoke(body: RuntimeInvokeRequest) -> RuntimeInvokeResponse:
    """Invoke the agent runtime synchronously.

    Routes to OrchestratorRuntime when ``orchestrate=True``.
    504 on timeout (default 300s matches agent config).
    """
    if body.orchestrate:
        from silkroute.mantis.runtime.interface import RuntimeType

        runtime = get_runtime(RuntimeType.ORCHESTRATOR)
    else:
        runtime = get_runtime(body.runtime_type)

    config = RuntimeConfig(
        model_override=body.model_override,
        max_iterations=body.max_iterations,
        budget_limit_usd=body.budget_limit_usd,
    )

    try:
        result = await asyncio.wait_for(
            runtime.invoke(body.task, config),
            timeout=300,
        )
    except TimeoutError as exc:
        raise HTTPException(status_code=504, detail="Runtime invoke timed out (300s)") from exc

    return RuntimeInvokeResponse(
        status=result.status,
        session_id=result.session_id,
        output=result.output,
        iterations=result.iterations,
        cost_usd=result.cost_usd,
        error=result.error,
    )


async def _stream_events(
    task: str,
    runtime_type: str | None,
    timeout_seconds: int = 300,
) -> AsyncIterator[str]:
    """Generate SSE events from runtime stream with server-side timeout."""
    runtime = get_runtime(runtime_type)
    config = RuntimeConfig()

    try:
        async with asyncio.timeout(timeout_seconds):
            async for chunk in runtime.stream(task, config):
                yield f"data: {chunk}\n\n"
        yield "data: [DONE]\n\n"
    except TimeoutError:
        yield "data: [ERROR] Stream timed out\n\n"
    except Exception as exc:
        yield f"data: [ERROR] {exc}\n\n"


@router.get("/stream")
async def runtime_stream(
    task: str = Query(..., min_length=1),
    runtime_type: str | None = Query(default=None),
    api_config: ApiConfig = Depends(get_api_config),
) -> StreamingResponse:
    """Stream agent output via Server-Sent Events.

    Client connects with EventSource or curl:
        curl -N 'localhost:8787/runtime/stream?task=hello'
    """
    return StreamingResponse(
        _stream_events(task, runtime_type, api_config.stream_timeout_seconds),
        media_type="text/event-stream",
        headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"},
    )
