"""Task queue endpoints — submit, poll results, queue status.

POST /tasks       → Submit a task to the Redis queue
GET  /tasks/queue/status → Queue depth + counters
GET  /tasks/{task_id}/result → Poll for a specific task's result
"""

from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException

from silkroute.api.auth import require_auth
from silkroute.api.deps import get_queue
from silkroute.api.models import (
    QueueStatusResponse,
    TaskResultResponse,
    TaskSubmitRequest,
    TaskSubmitResponse,
)
from silkroute.daemon.queue import TaskQueue, TaskRequest

router = APIRouter(prefix="/tasks", tags=["tasks"], dependencies=[Depends(require_auth)])


@router.post("", status_code=201)
async def submit_task(
    body: TaskSubmitRequest,
    queue: TaskQueue = Depends(get_queue),
) -> TaskSubmitResponse:
    """Submit a task to the agent queue.

    Returns 201 with the task ID on success.
    Returns 429 if the queue is full (backpressure).
    """
    request = TaskRequest(
        task=body.task,
        project_id=body.project_id,
        model_override=body.model_override,
        tier_override=body.tier_override,
        max_iterations=body.max_iterations,
        budget_limit_usd=body.budget_limit_usd,
    )

    try:
        task_id = await queue.submit(request)
    except RuntimeError as exc:
        raise HTTPException(status_code=429, detail=str(exc)) from exc

    return TaskSubmitResponse(id=task_id)


@router.get("/queue/status")
async def queue_status(
    queue: TaskQueue = Depends(get_queue),
) -> QueueStatusResponse:
    """Get queue depth and counters."""
    pending = await queue.pending_count()
    return QueueStatusResponse(
        pending=pending,
        total_submitted=queue.total_submitted,
        total_completed=queue.total_completed,
    )


@router.get("/{task_id}/result")
async def get_task_result(
    task_id: str,
    queue: TaskQueue = Depends(get_queue),
) -> TaskResultResponse:
    """Poll for a task's result.

    Returns 404 if the task hasn't completed yet or doesn't exist.
    """
    result = await queue.get_result(task_id)
    if result is None:
        raise HTTPException(status_code=404, detail="Result not found (task pending or unknown)")

    return TaskResultResponse(
        request_id=result.request_id,
        status=result.status,
        session_id=result.session_id,
        cost_usd=result.cost_usd,
        iterations=result.iterations,
        duration_ms=result.duration_ms,
        error=result.error,
    )
