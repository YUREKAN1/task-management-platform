from fastapi import APIRouter, Depends, Path, Query, status
from sqlalchemy.orm import Session
from typing import Literal, Optional
from uuid import UUID
from datetime import datetime

from app.api.deps import get_db, get_current_user
from app.models.enums import TaskStatus, TaskPriority
from app.schemas.task import (
    TaskCreate,
    ProjectTaskCreate,
    TaskUpdate,
    TaskAssignmentUpdate,
    TaskResponse,
    PaginatedTaskResponse,
)
from app.services import task as task_service
from app.models.user import User

router = APIRouter()

# Literal types used for sort parameters.  FastAPI validates these at
# request-parse time and returns HTTP 422 for invalid values, consistent
# with how all other enum query params behave in this project.
SortByField = Literal["created_at", "updated_at", "due_date", "priority", "status", "title"]
SortOrder   = Literal["asc", "desc"]


# ─── Personal tasks ──────────────────────────────────────────────────────────

@router.post(
    "/tasks",
    response_model=TaskResponse,
    status_code=status.HTTP_201_CREATED,
    summary="Create Personal Task",
    responses={
        201: {"description": "Personal task created successfully."},
        401: {"description": "Missing, invalid, or expired JWT Bearer token."},
        422: {"description": "Validation error (e.g. empty task title)."},
    },
)
def create_personal_task(
    task_in: TaskCreate,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """
    Creates a private personal task owned by the authenticated caller (`project_id = null`, `assigned_to = null`).
    Records a `TASK_CREATED` audit event.
    """
    return task_service.create_personal_task(db, task_in=task_in, user=current_user)


@router.get(
    "/tasks",
    response_model=PaginatedTaskResponse,
    summary="List Personal Tasks",
    responses={
        200: {"description": "Paginated list of personal tasks owned by the caller."},
        401: {"description": "Missing, invalid, or expired JWT Bearer token."},
        422: {"description": "Invalid query parameters (e.g. invalid sort field or pagination bounds)."},
    },
)
def list_personal_tasks(
    page: int = Query(1, ge=1, description="Page number (>= 1)"),
    page_size: int = Query(20, ge=1, le=100, description="Items per page (1 to 100)"),
    search: Optional[str] = Query(None, description="Case-insensitive search in title or description"),
    status: Optional[TaskStatus] = Query(None, description="Filter by status (TODO, IN_PROGRESS, COMPLETED)"),
    priority: Optional[TaskPriority] = Query(None, description="Filter by priority (LOW, MEDIUM, HIGH)"),
    assigned_to: Optional[UUID] = Query(None, description="Filter by assigned user UUID"),
    due_before: Optional[datetime] = Query(None, description="Filter tasks due on or before this timestamp"),
    due_after: Optional[datetime] = Query(None, description="Filter tasks due on or after this timestamp"),
    sort_by: SortByField = Query("created_at", description="Sort field: created_at, updated_at, due_date, priority, status, title"),
    sort_order: SortOrder = Query("desc", description="Sort direction: asc or desc"),
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """
    Retrieves a paginated list of personal tasks belonging exclusively to the authenticated caller.
    Supports case-insensitive full-text search, multi-field filtering, and deterministic sorting.
    """
    return task_service.list_personal_tasks(
        db=db,
        user=current_user,
        page=page,
        page_size=page_size,
        search=search,
        status=status,
        priority=priority,
        assigned_to=assigned_to,
        due_before=due_before,
        due_after=due_after,
        sort_by=sort_by,
        sort_order=sort_order,
    )


@router.get(
    "/tasks/{task_id}",
    response_model=TaskResponse,
    summary="Get Task Details",
    responses={
        200: {"description": "Task details retrieved successfully."},
        401: {"description": "Missing, invalid, or expired JWT Bearer token."},
        403: {"description": "User is not authorized to view this task."},
        404: {"description": "Task not found."},
        422: {"description": "Invalid UUID format."},
    },
)
def get_task(
    task_id: UUID = Path(..., description="Unique UUID identifier of the task"),
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """
    Retrieves details for a personal or project task.
    - Personal tasks: Accessible only by the task creator.
    - Project tasks: Accessible by any member of the parent team or global `ADMIN`.
    """
    return task_service.get_task(db, task_id=task_id, user=current_user)


@router.patch(
    "/tasks/{task_id}",
    response_model=TaskResponse,
    summary="Update Task",
    responses={
        200: {"description": "Task updated successfully."},
        401: {"description": "Missing, invalid, or expired JWT Bearer token."},
        403: {"description": "User is not authorized to edit this task."},
        404: {"description": "Task not found."},
        422: {"description": "Validation error (e.g. empty title string or invalid status/priority enum)."},
    },
)
def update_task(
    task_id: UUID = Path(..., description="Unique UUID identifier of the task"),
    task_in: TaskUpdate = ...,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """
    Updates mutable task properties (`title`, `description`, `status`, `priority`, `due_date`).
    - Personal tasks: Editable only by the creator.
    - Project tasks: Editable by team `MANAGER`, the current `assigned_to` member, or global `ADMIN`.
    - Automatically manages `completed_at`: sets to current timestamp upon `COMPLETED`, clears upon reopen.
    - Records appropriate audit events (`TASK_UPDATED`, `TASK_COMPLETED`, or `TASK_REOPENED`).
    """
    return task_service.update_task(db, task_id=task_id, task_in=task_in, user=current_user)


@router.patch(
    "/tasks/{task_id}/assignment",
    response_model=TaskResponse,
    summary="Assign or Unassign Task",
    responses={
        200: {"description": "Task assignment updated successfully."},
        400: {"description": "Invalid assignment (e.g. personal tasks cannot be assigned, or target user is inactive or outside the team)."},
        401: {"description": "Missing, invalid, or expired JWT Bearer token."},
        403: {"description": "Caller lacks team MANAGER privileges."},
        404: {"description": "Task or assignee user not found."},
        422: {"description": "Invalid UUID format."},
    },
)
def assign_task(
    task_id: UUID = Path(..., description="Unique UUID identifier of the project task"),
    assign_in: TaskAssignmentUpdate = ...,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """
    Assigns or unassigns a project task.
    - Only project tasks can be assigned; personal tasks return 400 Bad Request.
    - Requires team `MANAGER` or global `ADMIN`.
    - Assignee must be an active member of the project's parent team.
    - Setting `assigned_to: null` unassigns the task.
    - Records a `TASK_ASSIGNED` or `TASK_UNASSIGNED` audit event.
    """
    return task_service.assign_task(db, task_id=task_id, assign_in=assign_in, user=current_user)


@router.delete(
    "/tasks/{task_id}",
    status_code=status.HTTP_204_NO_CONTENT,
    summary="Delete Task",
    responses={
        204: {"description": "Task successfully deleted."},
        401: {"description": "Missing, invalid, or expired JWT Bearer token."},
        403: {"description": "User is not authorized to delete this task."},
        404: {"description": "Task not found."},
        422: {"description": "Invalid UUID format."},
    },
)
def delete_task(
    task_id: UUID = Path(..., description="Unique UUID identifier of the task to delete"),
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """
    Deletes a task.
    - Personal tasks: Deletable only by the creator.
    - Project tasks: Deletable only by team `MANAGER` or global `ADMIN`.
    - Records a `TASK_DELETED` audit event.
    """
    task_service.delete_task(db, task_id=task_id, user=current_user)
    return None


# ─── Project tasks ────────────────────────────────────────────────────────────

@router.post(
    "/projects/{project_id}/tasks",
    response_model=TaskResponse,
    status_code=status.HTTP_201_CREATED,
    summary="Create Project Task",
    responses={
        201: {"description": "Project task created successfully."},
        400: {"description": "Invalid assignee (user is inactive or not a member of the project's team)."},
        401: {"description": "Missing, invalid, or expired JWT Bearer token."},
        403: {"description": "Caller lacks team MANAGER privileges or global ADMIN role."},
        404: {"description": "Project or assignee user not found."},
        422: {"description": "Validation error (e.g. empty title string or invalid UUID)."},
    },
)
def create_project_task(
    project_id: UUID = Path(..., description="Unique UUID identifier of the project"),
    task_in: ProjectTaskCreate = ...,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """
    Creates a new task scoped to a project.
    - Requires team `MANAGER` or global `ADMIN`.
    - If `assigned_to` is provided, the target user must be an active member of the project's parent team.
    - Records a `TASK_CREATED` audit event.
    """
    return task_service.create_project_task(db, project_id=project_id, task_in=task_in, user=current_user)


@router.get(
    "/projects/{project_id}/tasks",
    response_model=PaginatedTaskResponse,
    summary="List Project Tasks",
    responses={
        200: {"description": "Paginated list of tasks belonging to the project."},
        401: {"description": "Missing, invalid, or expired JWT Bearer token."},
        403: {"description": "Caller is not a member of the project's team and not a global ADMIN."},
        404: {"description": "Project not found."},
        422: {"description": "Invalid query parameters or UUID format."},
    },
)
def list_project_tasks(
    project_id: UUID = Path(..., description="Unique UUID identifier of the project"),
    page: int = Query(1, ge=1, description="Page number (>= 1)"),
    page_size: int = Query(20, ge=1, le=100, description="Items per page (1 to 100)"),
    search: Optional[str] = Query(None, description="Case-insensitive search in title or description"),
    status: Optional[TaskStatus] = Query(None, description="Filter by status (TODO, IN_PROGRESS, COMPLETED)"),
    priority: Optional[TaskPriority] = Query(None, description="Filter by priority (LOW, MEDIUM, HIGH)"),
    assigned_to: Optional[UUID] = Query(None, description="Filter by assigned user UUID"),
    due_before: Optional[datetime] = Query(None, description="Filter tasks due on or before this timestamp"),
    due_after: Optional[datetime] = Query(None, description="Filter tasks due on or after this timestamp"),
    sort_by: SortByField = Query("created_at", description="Sort field: created_at, updated_at, due_date, priority, status, title"),
    sort_order: SortOrder = Query("desc", description="Sort direction: asc or desc"),
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """
    Retrieves a paginated list of tasks scoped to the specified project.
    - Accessible by members of the parent team or global `ADMIN`.
    - Supports full-text search, status/priority/assignee/due_date filtering, and multi-field sorting.
    """
    return task_service.list_project_tasks(
        db=db,
        project_id=project_id,
        user=current_user,
        page=page,
        page_size=page_size,
        search=search,
        status=status,
        priority=priority,
        assigned_to=assigned_to,
        due_before=due_before,
        due_after=due_after,
        sort_by=sort_by,
        sort_order=sort_order,
    )
