"""Supervisor session endpoints — create, query, resume, cancel.

POST /supervisor/sessions       → Create and execute a supervisor workflow
GET  /supervisor/sessions/{id}  → Query session status
POST /supervisor/sessions/{id}/resume → Resume a paused/failed session
DELETE /supervisor/sessions/{id} → Cancel a session
"""

from __future__ import annotations

from typing import TYPE_CHECKING

from fastapi import APIRouter, Depends, HTTPException

from silkroute.api.auth import require_auth
from silkroute.api.deps import get_db_pool, get_settings

if TYPE_CHECKING:
    import asyncpg
from silkroute.api.models import (
    SupervisorSessionCreateRequest,
    SupervisorSessionResponse,
    SupervisorStepResponse,
)
from silkroute.config.settings import SilkRouteSettings
from silkroute.mantis.runtime.interface import RuntimeConfig
from silkroute.mantis.supervisor.models import (
    SupervisorPlan,
    SupervisorStep,
)
from silkroute.mantis.supervisor.runtime import SupervisorRuntime

router = APIRouter(
    prefix="/supervisor",
    tags=["supervisor"],
    dependencies=[Depends(require_auth)],
)


@router.post("/sessions")
async def create_session(
    body: SupervisorSessionCreateRequest,
    settings: SilkRouteSettings = Depends(get_settings),
    db_pool: asyncpg.Pool | None = Depends(get_db_pool),  # noqa: B008
) -> SupervisorSessionResponse:
    """Create and execute a supervisor workflow."""
    steps = [
        SupervisorStep(
            name=s.name,
            description=s.description,
            depends_on=s.depends_on,
            runtime_type=s.runtime_type,
            max_retries=s.max_retries,
            condition=s.condition,
        )
        for s in body.steps
    ]

    plan = SupervisorPlan(
        project_id=body.project_id,
        description=body.description,
        steps=steps,
        total_budget_usd=body.total_budget_usd,
        timeout_seconds=body.timeout_seconds,
    )

    rt = SupervisorRuntime(
        supervisor_config=settings.supervisor,
        db_pool=db_pool,
    )

    session = await rt.create_session(plan, project_id=body.project_id)
    result = await rt._run_session(session, RuntimeConfig(
        project_id=body.project_id,
        budget_limit_usd=body.total_budget_usd,
    ))

    return SupervisorSessionResponse(
        id=session.id,
        project_id=session.project_id,
        status=session.status.value,
        total_cost_usd=result.cost_usd,
        steps=[
            SupervisorStepResponse(
                id=s.id,
                name=s.name,
                status=s.status.value,
                cost_usd=s.cost_usd,
                output=s.output,
                error=s.error,
                retry_count=s.retry_count,
            )
            for s in session.plan.steps
        ],
        created_at=session.created_at.isoformat(),
        updated_at=session.updated_at.isoformat(),
        error=session.error,
    )


@router.get("/sessions/{session_id}")
async def get_session(
    session_id: str,
    db_pool: asyncpg.Pool | None = Depends(get_db_pool),  # noqa: B008
) -> SupervisorSessionResponse:
    """Query a supervisor session by ID."""
    if db_pool is None:
        raise HTTPException(status_code=503, detail="Database unavailable")

    from silkroute.db.repositories.supervisor import get_supervisor_session

    session = await get_supervisor_session(db_pool, session_id)
    if session is None:
        raise HTTPException(status_code=404, detail=f"Session {session_id} not found")

    return SupervisorSessionResponse(
        id=session.id,
        project_id=session.project_id,
        status=session.status.value,
        total_cost_usd=session.total_cost_usd,
        steps=[
            SupervisorStepResponse(
                id=s.id,
                name=s.name,
                status=s.status.value,
                cost_usd=s.cost_usd,
                output=s.output,
                error=s.error,
                retry_count=s.retry_count,
            )
            for s in session.plan.steps
        ],
        created_at=session.created_at.isoformat(),
        updated_at=session.updated_at.isoformat(),
        error=session.error,
    )


@router.post("/sessions/{session_id}/resume")
async def resume_session(
    session_id: str,
    settings: SilkRouteSettings = Depends(get_settings),
    db_pool: asyncpg.Pool | None = Depends(get_db_pool),  # noqa: B008
) -> SupervisorSessionResponse:
    """Resume a paused or failed supervisor session."""
    rt = SupervisorRuntime(
        supervisor_config=settings.supervisor,
        db_pool=db_pool,
    )
    result = await rt.resume_session(session_id)

    if result.status == "failed" and "not found" in result.error.lower():
        raise HTTPException(status_code=404, detail=result.error)

    return SupervisorSessionResponse(
        id=session_id,
        project_id="",
        status=result.status,
        total_cost_usd=result.cost_usd,
        steps=[],
        created_at="",
        updated_at="",
        error=result.error,
    )


@router.delete("/sessions/{session_id}")
async def cancel_session(
    session_id: str,
    settings: SilkRouteSettings = Depends(get_settings),
    db_pool: asyncpg.Pool | None = Depends(get_db_pool),  # noqa: B008
) -> dict:
    """Cancel a supervisor session."""
    rt = SupervisorRuntime(
        supervisor_config=settings.supervisor,
        db_pool=db_pool,
    )
    success = await rt.cancel_session(session_id)
    if not success:
        raise HTTPException(status_code=404, detail=f"Session {session_id} not found")
    return {"status": "cancelled", "session_id": session_id}
