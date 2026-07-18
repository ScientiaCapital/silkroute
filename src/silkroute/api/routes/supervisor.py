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
    SupervisorSession,
    SupervisorStep,
)
from silkroute.mantis.supervisor.runtime import SupervisorRuntime

router = APIRouter(
    prefix="/supervisor",
    tags=["supervisor"],
    dependencies=[Depends(require_auth)],
)


def _steps_to_response(steps: list[SupervisorStep]) -> list[SupervisorStepResponse]:
    return [
        SupervisorStepResponse(
            id=s.id,
            name=s.name,
            status=s.status.value,
            cost_usd=s.cost_usd,
            output=s.output,
            error=s.error,
            retry_count=s.retry_count,
        )
        for s in steps
    ]


def _session_to_response(
    session: SupervisorSession,
    *,
    total_cost_usd: float | None = None,
) -> SupervisorSessionResponse:
    return SupervisorSessionResponse(
        id=session.id,
        project_id=session.project_id,
        status=session.status.value,
        total_cost_usd=(
            total_cost_usd if total_cost_usd is not None else session.total_cost_usd
        ),
        steps=_steps_to_response(session.plan.steps),
        created_at=session.created_at.isoformat(),
        updated_at=session.updated_at.isoformat(),
        error=session.error,
    )


@router.get("/sessions")
async def list_sessions(
    project_id: str | None = None,
    status: str | None = None,
    limit: int = 50,
    db_pool: asyncpg.Pool | None = Depends(get_db_pool),  # noqa: B008
) -> list[SupervisorSessionResponse]:
    """List supervisor sessions with optional filters."""
    if db_pool is None:
        raise HTTPException(status_code=503, detail="Database unavailable")

    from silkroute.db.repositories.supervisor import list_supervisor_sessions

    sessions = await list_supervisor_sessions(
        db_pool, project_id=project_id, status=status, limit=limit,
    )
    return [_session_to_response(s) for s in sessions]


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

    return _session_to_response(session, total_cost_usd=result.cost_usd)


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

    return _session_to_response(session)


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
