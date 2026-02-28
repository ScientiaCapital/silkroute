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
from silkroute.api.models import RuntimeInvokeRequest, RuntimeInvokeResponse
from silkroute.mantis.runtime.interface import RuntimeConfig
from silkroute.mantis.runtime.registry import get_runtime

router = APIRouter(prefix="/runtime", tags=["runtime"], dependencies=[Depends(require_auth)])


@router.post("/invoke")
async def runtime_invoke(body: RuntimeInvokeRequest) -> RuntimeInvokeResponse:
    """Invoke the agent runtime synchronously.

    Returns the full result once the agent completes.
    504 on timeout (default 300s matches agent config).
    """
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
) -> AsyncIterator[str]:
    """Generate SSE events from runtime stream."""
    runtime = get_runtime(runtime_type)
    config = RuntimeConfig()

    try:
        async for chunk in runtime.stream(task, config):
            yield f"data: {chunk}\n\n"
        yield "data: [DONE]\n\n"
    except Exception as exc:
        yield f"data: [ERROR] {exc}\n\n"


@router.get("/stream")
async def runtime_stream(
    task: str = Query(..., min_length=1),
    runtime_type: str | None = Query(default=None),
) -> StreamingResponse:
    """Stream agent output via Server-Sent Events.

    Client connects with EventSource or curl:
        curl -N 'localhost:8787/runtime/stream?task=hello'
    """
    return StreamingResponse(
        _stream_events(task, runtime_type),
        media_type="text/event-stream",
        headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"},
    )
