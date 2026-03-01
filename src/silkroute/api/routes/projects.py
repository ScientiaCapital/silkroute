"""Project management endpoints — CRUD for project budget governance.

POST   /projects            → Create a new project
GET    /projects            → List all projects
GET    /projects/{id}       → Get a single project
PATCH  /projects/{id}       → Partially update a project
DELETE /projects/{id}       → Delete a project (blocks "default")
"""

from __future__ import annotations

from typing import TYPE_CHECKING

import asyncpg
from fastapi import APIRouter, Depends, HTTPException

from silkroute.api.auth import require_auth
from silkroute.api.deps import get_db_pool
from silkroute.api.models import (
    ProjectCreateRequest,
    ProjectListResponse,
    ProjectResponse,
    ProjectUpdateRequest,
)
from silkroute.db.repositories.projects import (
    create_project,
    delete_project,
    get_project,
    list_projects,
    update_project,
)

if TYPE_CHECKING:
    pass

router = APIRouter(
    prefix="/projects",
    tags=["projects"],
    dependencies=[Depends(require_auth)],
)


@router.post("", status_code=201)
async def create_project_endpoint(
    body: ProjectCreateRequest,
    db_pool: asyncpg.Pool | None = Depends(get_db_pool),  # noqa: B008
) -> ProjectResponse:
    """Create a new project with budget governance."""
    if db_pool is None:
        raise HTTPException(status_code=503, detail="Database unavailable")
    try:
        row = await create_project(
            db_pool,
            project_id=body.id,
            name=body.name,
            description=body.description,
            github_repo=body.github_repo,
            budget_monthly_usd=body.budget_monthly_usd,
            budget_daily_usd=body.budget_daily_usd,
        )
    except asyncpg.UniqueViolationError:
        raise HTTPException(status_code=409, detail=f"Project '{body.id}' already exists") from None
    return _to_response(row)


@router.get("")
async def list_projects_endpoint(
    db_pool: asyncpg.Pool | None = Depends(get_db_pool),  # noqa: B008
) -> ProjectListResponse:
    """List all projects (fail-open: empty list if DB unavailable)."""
    if db_pool is None:
        return ProjectListResponse(projects=[], total=0)
    rows = await list_projects(db_pool)
    projects = [_to_response(r) for r in rows]
    return ProjectListResponse(projects=projects, total=len(projects))


@router.get("/{project_id}")
async def get_project_endpoint(
    project_id: str,
    db_pool: asyncpg.Pool | None = Depends(get_db_pool),  # noqa: B008
) -> ProjectResponse:
    """Get a single project by ID."""
    if db_pool is None:
        raise HTTPException(status_code=503, detail="Database unavailable")
    row = await get_project(db_pool, project_id)
    if row is None:
        raise HTTPException(status_code=404, detail=f"Project '{project_id}' not found")
    return _to_response(row)


@router.patch("/{project_id}")
async def update_project_endpoint(
    project_id: str,
    body: ProjectUpdateRequest,
    db_pool: asyncpg.Pool | None = Depends(get_db_pool),  # noqa: B008
) -> ProjectResponse:
    """Partially update a project."""
    if db_pool is None:
        raise HTTPException(status_code=503, detail="Database unavailable")
    row = await update_project(
        db_pool,
        project_id,
        name=body.name,
        description=body.description,
        github_repo=body.github_repo,
        budget_monthly_usd=body.budget_monthly_usd,
        budget_daily_usd=body.budget_daily_usd,
    )
    if row is None:
        raise HTTPException(status_code=404, detail=f"Project '{project_id}' not found")
    return _to_response(row)


@router.delete("/{project_id}")
async def delete_project_endpoint(
    project_id: str,
    db_pool: asyncpg.Pool | None = Depends(get_db_pool),  # noqa: B008
) -> dict:
    """Delete a project. Blocks deletion of 'default' project."""
    if db_pool is None:
        raise HTTPException(status_code=503, detail="Database unavailable")
    try:
        deleted = await delete_project(db_pool, project_id)
    except ValueError as exc:
        raise HTTPException(
            status_code=400 if "default" in str(exc) else 409,
            detail=str(exc),
        ) from None
    if not deleted:
        raise HTTPException(status_code=404, detail=f"Project '{project_id}' not found")
    return {"status": "deleted", "project_id": project_id}


def _to_response(row: dict) -> ProjectResponse:
    """Convert a DB row dict to a ProjectResponse."""
    return ProjectResponse(
        id=row["id"],
        name=row["name"],
        description=row.get("description", ""),
        github_repo=row.get("github_repo", ""),
        budget_monthly_usd=float(row["budget_monthly_usd"]),
        budget_daily_usd=float(row["budget_daily_usd"]),
        created_at=str(row.get("created_at", "")),
        updated_at=str(row.get("updated_at", "")),
    )
