from datetime import datetime, timezone
from uuid import UUID
from typing import Optional

from fastapi import HTTPException, status
from sqlalchemy import or_
from sqlalchemy.orm import Session

from app.models.task import Task
from app.models.user import User
from app.models.team import TeamMember
from app.models.enums import TaskStatus, TaskPriority, TeamRole, GlobalRole, AuditAction
from app.schemas.task import TaskCreate, ProjectTaskCreate, TaskUpdate, TaskAssignmentUpdate
from app.services.project import get_project_or_404
from app.services.team import require_team_member, require_team_manager
from app.services.audit import create_audit_log


SORT_FIELDS = {
    "created_at": Task.created_at,
    "updated_at": Task.updated_at,
    "due_date": Task.due_date,
    "priority": Task.priority,
    "status": Task.status,
    "title": Task.title,
}


def _apply_task_filters_and_sort(
    query,
    search: Optional[str] = None,
    status_filter: Optional[TaskStatus] = None,
    priority: Optional[TaskPriority] = None,
    assigned_to: Optional[UUID] = None,
    due_before: Optional[datetime] = None,
    due_after: Optional[datetime] = None,
    sort_by: str = "created_at",
    sort_order: str = "desc",
):
    if search and search.strip():
        term = f"%{search.strip()}%"
        query = query.filter(
            or_(
                Task.title.ilike(term),
                Task.description.ilike(term),
            )
        )
    if status_filter is not None:
        query = query.filter(Task.status == status_filter)
    if priority is not None:
        query = query.filter(Task.priority == priority)
    if assigned_to is not None:
        query = query.filter(Task.assigned_to == assigned_to)
    if due_before is not None:
        query = query.filter(Task.due_date <= due_before)
    if due_after is not None:
        query = query.filter(Task.due_date >= due_after)

    # sort_by and sort_order are validated as Literal types by FastAPI before
    # this function is called, so no runtime check is needed here.
    column = SORT_FIELDS[sort_by]
    if sort_order.lower() == "asc":
        order_clause = column.asc()
    else:
        order_clause = column.desc()

    # Deterministic secondary sorting by id
    query = query.order_by(order_clause, Task.id.desc())
    return query


# ─── Internal helpers ────────────────────────────────────────────────────────

def _get_task_or_404(db: Session, task_id: UUID) -> Task:
    task = db.query(Task).filter(Task.id == task_id).first()
    if not task:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Task not found")
    return task


def _apply_completed_at(task: Task) -> None:
    """Enforce completed_at invariant based on current status."""
    if task.status == TaskStatus.COMPLETED:
        if task.completed_at is None:
            task.completed_at = datetime.now(timezone.utc)
    else:
        task.completed_at = None


def _assert_personal_task_owner(task: Task, user: User) -> None:
    if task.created_by != user.id:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Not authorised")


def _assert_project_task_member(db: Session, task: Task, user: User) -> None:
    project = get_project_or_404(db, task.project_id)
    if user.global_role == GlobalRole.ADMIN:
        return
    require_team_member(db, project.team_id, user.id)


def _assert_project_task_manager(db: Session, task: Task, user: User) -> None:
    project = get_project_or_404(db, task.project_id)
    if user.global_role == GlobalRole.ADMIN:
        return
    require_team_manager(db, project.team_id, user.id)


def _validate_assignee(db: Session, team_id: UUID, assignee_id: UUID) -> None:
    assignee = db.query(User).filter(User.id == assignee_id).first()
    if not assignee:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Assigned user not found")
    if not assignee.is_active or assignee.deleted_at is not None:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Assigned user is inactive")
    membership = db.query(TeamMember).filter(
        TeamMember.team_id == team_id,
        TeamMember.user_id == assignee_id,
    ).first()
    if not membership:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Assigned user is not a member of this project's team",
        )


# ─── Personal task operations ─────────────────────────────────────────────────

def create_personal_task(db: Session, task_in: TaskCreate, user: User) -> Task:
    task = Task(
        title=task_in.title,
        description=task_in.description,
        priority=task_in.priority,
        due_date=task_in.due_date,
        created_by=user.id,
        project_id=None,
        assigned_to=None,
    )
    _apply_completed_at(task)
    db.add(task)
    db.flush()

    create_audit_log(
        db=db,
        actor_id=user.id,
        action=AuditAction.TASK_CREATED,
        entity_type="task",
        entity_id=task.id,
        team_id=None,
        description=f"Personal task '{task.title}' created",
        metadata={"title": task.title, "priority": task.priority.value if hasattr(task.priority, "value") else str(task.priority)},
    )

    db.commit()
    db.refresh(task)
    return task


def list_personal_tasks(
    db: Session,
    user: User,
    page: int = 1,
    page_size: int = 20,
    search: Optional[str] = None,
    status: Optional[TaskStatus] = None,
    priority: Optional[TaskPriority] = None,
    assigned_to: Optional[UUID] = None,
    due_before: Optional[datetime] = None,
    due_after: Optional[datetime] = None,
    sort_by: str = "created_at",
    sort_order: str = "desc",
):
    query = db.query(Task).filter(Task.created_by == user.id, Task.project_id.is_(None))
    query = _apply_task_filters_and_sort(
        query,
        search=search,
        status_filter=status,
        priority=priority,
        assigned_to=assigned_to,
        due_before=due_before,
        due_after=due_after,
        sort_by=sort_by,
        sort_order=sort_order,
    )
    total = query.count()
    offset = (page - 1) * page_size
    items = query.offset(offset).limit(page_size).all()
    total_pages = (total + page_size - 1) // page_size if total > 0 else 0
    return {
        "items": items,
        "page": page,
        "page_size": page_size,
        "total": total,
        "total_pages": total_pages,
    }


# ─── Project task operations ──────────────────────────────────────────────────

def create_project_task(db: Session, project_id: UUID, task_in: ProjectTaskCreate, user: User) -> Task:
    project = get_project_or_404(db, project_id)
    if user.global_role != GlobalRole.ADMIN:
        require_team_manager(db, project.team_id, user.id)

    if task_in.assigned_to is not None:
        _validate_assignee(db, project.team_id, task_in.assigned_to)

    task = Task(
        title=task_in.title,
        description=task_in.description,
        priority=task_in.priority,
        due_date=task_in.due_date,
        project_id=project_id,
        created_by=user.id,
        assigned_to=task_in.assigned_to,
    )
    _apply_completed_at(task)
    db.add(task)
    db.flush()

    create_audit_log(
        db=db,
        actor_id=user.id,
        action=AuditAction.TASK_CREATED,
        entity_type="task",
        entity_id=task.id,
        team_id=project.team_id,
        description=f"Project task '{task.title}' created",
        metadata={"title": task.title, "priority": task.priority.value if hasattr(task.priority, "value") else str(task.priority), "project_id": str(project_id)},
    )

    db.commit()
    db.refresh(task)
    return task


def list_project_tasks(
    db: Session,
    project_id: UUID,
    user: User,
    page: int = 1,
    page_size: int = 20,
    search: Optional[str] = None,
    status: Optional[TaskStatus] = None,
    priority: Optional[TaskPriority] = None,
    assigned_to: Optional[UUID] = None,
    due_before: Optional[datetime] = None,
    due_after: Optional[datetime] = None,
    sort_by: str = "created_at",
    sort_order: str = "desc",
):
    project = get_project_or_404(db, project_id)
    if user.global_role != GlobalRole.ADMIN:
        require_team_member(db, project.team_id, user.id)

    query = db.query(Task).filter(Task.project_id == project_id)
    query = _apply_task_filters_and_sort(
        query,
        search=search,
        status_filter=status,
        priority=priority,
        assigned_to=assigned_to,
        due_before=due_before,
        due_after=due_after,
        sort_by=sort_by,
        sort_order=sort_order,
    )
    total = query.count()
    offset = (page - 1) * page_size
    items = query.offset(offset).limit(page_size).all()
    total_pages = (total + page_size - 1) // page_size if total > 0 else 0
    return {
        "items": items,
        "page": page,
        "page_size": page_size,
        "total": total,
        "total_pages": total_pages,
    }


# ─── Single task ──────────────────────────────────────────────────────────────

def get_task(db: Session, task_id: UUID, user: User) -> Task:
    task = _get_task_or_404(db, task_id)
    if task.project_id is None:
        _assert_personal_task_owner(task, user)
    else:
        _assert_project_task_member(db, task, user)
    return task


# ─── Update task ──────────────────────────────────────────────────────────────

def update_task(db: Session, task_id: UUID, task_in: TaskUpdate, user: User) -> Task:
    task = _get_task_or_404(db, task_id)

    team_id = None
    if task.project_id is None:
        # Personal task — only creator can update
        _assert_personal_task_owner(task, user)
    else:
        # Project task — manager, assignee, or admin may update
        project = get_project_or_404(db, task.project_id)
        team_id = project.team_id
        if user.global_role != GlobalRole.ADMIN:
            # Must be at least a team member
            require_team_member(db, project.team_id, user.id)
            # Non-assignees who are also not managers cannot update
            membership = db.query(TeamMember).filter(
                TeamMember.team_id == project.team_id,
                TeamMember.user_id == user.id,
            ).first()
            is_manager = membership and membership.role == TeamRole.MANAGER
            is_assignee = task.assigned_to == user.id
            if not is_manager and not is_assignee:
                raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Not authorised to update this task")

    old_status = task.status
    changes = {}
    if task_in.title is not None and task_in.title != task.title:
        changes["title"] = task_in.title
        task.title = task_in.title
    if task_in.description is not None and task_in.description != task.description:
        changes["description"] = task_in.description
        task.description = task_in.description
    if task_in.priority is not None and task_in.priority != task.priority:
        changes["priority"] = task_in.priority.value if hasattr(task_in.priority, "value") else str(task_in.priority)
        task.priority = task_in.priority
    if task_in.due_date is not None and task_in.due_date != task.due_date:
        changes["due_date"] = task_in.due_date.isoformat() if task_in.due_date else None
        task.due_date = task_in.due_date
    if task_in.status is not None and task_in.status != task.status:
        changes["status"] = task_in.status.value if hasattr(task_in.status, "value") else str(task_in.status)
        task.status = task_in.status

    _apply_completed_at(task)

    if task.status == TaskStatus.COMPLETED and old_status != TaskStatus.COMPLETED:
        create_audit_log(
            db=db,
            actor_id=user.id,
            action=AuditAction.TASK_COMPLETED,
            entity_type="task",
            entity_id=task.id,
            team_id=team_id,
            description=f"Task '{task.title}' completed",
            metadata={
                "old_status": old_status.value if hasattr(old_status, "value") else str(old_status),
                "new_status": task.status.value if hasattr(task.status, "value") else str(task.status),
            },
        )
    elif old_status == TaskStatus.COMPLETED and task.status != TaskStatus.COMPLETED:
        create_audit_log(
            db=db,
            actor_id=user.id,
            action=AuditAction.TASK_REOPENED,
            entity_type="task",
            entity_id=task.id,
            team_id=team_id,
            description=f"Task '{task.title}' reopened",
            metadata={
                "old_status": old_status.value if hasattr(old_status, "value") else str(old_status),
                "new_status": task.status.value if hasattr(task.status, "value") else str(task.status),
            },
        )
    else:
        create_audit_log(
            db=db,
            actor_id=user.id,
            action=AuditAction.TASK_UPDATED,
            entity_type="task",
            entity_id=task.id,
            team_id=team_id,
            description=f"Task '{task.title}' updated",
            metadata=changes,
        )

    db.commit()
    db.refresh(task)
    return task


# ─── Assignment ───────────────────────────────────────────────────────────────

def assign_task(db: Session, task_id: UUID, assign_in: TaskAssignmentUpdate, user: User) -> Task:
    task = _get_task_or_404(db, task_id)

    if task.project_id is None:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Cannot assign personal tasks to other users",
        )

    _assert_project_task_manager(db, task, user)

    project = get_project_or_404(db, task.project_id)
    if assign_in.assigned_to is not None:
        _validate_assignee(db, project.team_id, assign_in.assigned_to)

    old_assigned_to = task.assigned_to
    task.assigned_to = assign_in.assigned_to

    if assign_in.assigned_to is not None:
        create_audit_log(
            db=db,
            actor_id=user.id,
            action=AuditAction.TASK_ASSIGNED,
            entity_type="task",
            entity_id=task.id,
            team_id=project.team_id,
            description=f"Task '{task.title}' assigned to user {assign_in.assigned_to}",
            metadata={"assigned_to": str(assign_in.assigned_to)},
        )
    else:
        create_audit_log(
            db=db,
            actor_id=user.id,
            action=AuditAction.TASK_UNASSIGNED,
            entity_type="task",
            entity_id=task.id,
            team_id=project.team_id,
            description=f"Task '{task.title}' unassigned",
            metadata={"previous_assigned_to": str(old_assigned_to) if old_assigned_to else None},
        )

    db.commit()
    db.refresh(task)
    return task


# ─── Delete task ──────────────────────────────────────────────────────────────

def delete_task(db: Session, task_id: UUID, user: User) -> None:
    task = _get_task_or_404(db, task_id)

    team_id = None
    if task.project_id is None:
        _assert_personal_task_owner(task, user)
    else:
        _assert_project_task_manager(db, task, user)
        project = get_project_or_404(db, task.project_id)
        team_id = project.team_id

    create_audit_log(
        db=db,
        actor_id=user.id,
        action=AuditAction.TASK_DELETED,
        entity_type="task",
        entity_id=task.id,
        team_id=team_id,
        description=f"Task '{task.title}' deleted",
        metadata={"title": task.title, "project_id": str(task.project_id) if task.project_id else None},
    )

    db.delete(task)
    db.commit()
