from fastapi import APIRouter, Depends, Path, Query, status
from sqlalchemy.orm import Session
from typing import List
from uuid import UUID
from app.api.deps import get_db, get_current_user
from app.schemas.project import ProjectCreate, ProjectUpdate, ProjectResponse
from app.services import project as project_service
from app.models.user import User

router = APIRouter()

@router.post(
    "/teams/{team_id}/projects",
    response_model=ProjectResponse,
    status_code=status.HTTP_201_CREATED,
    summary="Create Team Project",
    responses={
        201: {"description": "Project created successfully within the team."},
        401: {"description": "Missing, invalid, or expired JWT Bearer token."},
        403: {"description": "Caller lacks team MANAGER privileges or global ADMIN role."},
        404: {"description": "Team not found."},
        422: {"description": "Validation error (e.g. empty project name or invalid UUID)."},
    },
)
def create_project(
    team_id: UUID = Path(..., description="Unique UUID identifier of the parent team"),
    project_in: ProjectCreate = ...,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    """
    Creates a new project scoped to the specified team. Requires team `MANAGER` or global `ADMIN`.
    The `created_by` attribute is bound to the authenticated caller. Records a `PROJECT_CREATED` audit event.
    """
    return project_service.create_project(db, team_id=team_id, project_in=project_in, user=current_user)

@router.get(
    "/teams/{team_id}/projects",
    response_model=List[ProjectResponse],
    summary="List Team Projects",
    responses={
        200: {"description": "List of active projects scoped to the team."},
        401: {"description": "Missing, invalid, or expired JWT Bearer token."},
        403: {"description": "Caller is not a member of the team and not a global ADMIN."},
        404: {"description": "Team not found."},
        422: {"description": "Invalid UUID format."},
    },
)
def list_team_projects(
    team_id: UUID = Path(..., description="Unique UUID identifier of the team"),
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    """
    Lists all non-deleted projects belonging to a team. Accessible by team members or global `ADMIN`.
    """
    return project_service.list_team_projects(db, team_id=team_id, user=current_user)

@router.get(
    "/projects/{project_id}",
    response_model=ProjectResponse,
    summary="Get Project Details",
    responses={
        200: {"description": "Project details retrieved successfully."},
        401: {"description": "Missing, invalid, or expired JWT Bearer token."},
        403: {"description": "Caller is not a member of the project's team and not a global ADMIN."},
        404: {"description": "Project not found or marked deleted."},
        422: {"description": "Invalid UUID format."},
    },
)
def get_project(
    project_id: UUID = Path(..., description="Unique UUID identifier of the project"),
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    """
    Retrieves project metadata. Accessible by members of the project's parent team or global `ADMIN`.
    """
    return project_service.get_project(db, project_id=project_id, user=current_user)

@router.patch(
    "/projects/{project_id}",
    response_model=ProjectResponse,
    summary="Update Project",
    responses={
        200: {"description": "Project updated successfully."},
        401: {"description": "Missing, invalid, or expired JWT Bearer token."},
        403: {"description": "Caller lacks team MANAGER privileges or global ADMIN role."},
        404: {"description": "Project not found."},
        422: {"description": "Validation error (e.g. empty name string or invalid UUID)."},
    },
)
def update_project(
    project_id: UUID = Path(..., description="Unique UUID identifier of the project"),
    project_in: ProjectUpdate = ...,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    """
    Updates mutable project fields (`name`, `description`). Protected attributes (`team_id`, `created_by`)
    cannot be modified. Requires team `MANAGER` or global `ADMIN`. Records a `PROJECT_UPDATED` audit event.
    """
    return project_service.update_project(db, project_id=project_id, project_in=project_in, user=current_user)

@router.delete(
    "/projects/{project_id}",
    status_code=status.HTTP_204_NO_CONTENT,
    summary="Delete Project",
    responses={
        204: {"description": "Project successfully soft-deleted."},
        400: {"description": "Confirmation query parameter `confirm=true` is missing or false."},
        401: {"description": "Missing, invalid, or expired JWT Bearer token."},
        403: {"description": "Caller lacks team MANAGER privileges or global ADMIN role."},
        404: {"description": "Project not found."},
        422: {"description": "Invalid UUID format."},
    },
)
def delete_project(
    project_id: UUID = Path(..., description="Unique UUID identifier of the project to delete"),
    confirm: bool = Query(
        False,
        description="Explicit confirmation flag required for project deletion. Must be set to `true`.",
    ),
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    """
    Soft-deletes a project (`deleted_at = now`). Guarded by an explicit confirmation requirement:
    requests without `?confirm=true` will fail with HTTP 400 Bad Request. Requires team `MANAGER`
    or global `ADMIN`. Records a `PROJECT_DELETED` audit event.
    """
    project_service.delete_project(db, project_id=project_id, confirm=confirm, user=current_user)
    return None
