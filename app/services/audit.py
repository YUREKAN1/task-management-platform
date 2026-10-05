from datetime import datetime
from typing import Optional
from uuid import UUID
from fastapi import HTTPException, status
from sqlalchemy.orm import Session

from app.models.audit_log import AuditLog
from app.models.enums import AuditAction, GlobalRole, TeamRole
from app.models.team import TeamMember
from app.models.user import User


def create_audit_log(
    db: Session,
    actor_id: UUID,
    action: AuditAction,
    entity_type: str,
    entity_id: UUID,
    team_id: Optional[UUID] = None,
    description: Optional[str] = None,
    metadata: Optional[dict] = None,
) -> AuditLog:
    """
    Creates an AuditLog record and adds it to the current DB session.
    Participates in the caller's transaction — does NOT commit independently.
    """
    log = AuditLog(
        actor_id=actor_id,
        action=action,
        entity_type=entity_type,
        entity_id=entity_id,
        team_id=team_id,
        description=description,
        metadata_=metadata,
    )
    db.add(log)
    return log


def list_audit_logs(
    db: Session,
    user: User,
    page: int = 1,
    page_size: int = 20,
    action: Optional[AuditAction] = None,
    entity_type: Optional[str] = None,
    actor_id: Optional[UUID] = None,
    entity_id: Optional[UUID] = None,
    date_from: Optional[datetime] = None,
    date_to: Optional[datetime] = None,
):
    """
    Lists audit logs with role-based access control, database-side filtering,
    deterministic ordering, and pagination.
    """
    # ─── RBAC Authorization ───────────────────────────────────────────────────
    if user.global_role == GlobalRole.ADMIN:
        query = db.query(AuditLog)
    else:
        # Find all teams where user is a manager
        managed_memberships = db.query(TeamMember.team_id).filter(
            TeamMember.user_id == user.id,
            TeamMember.role == TeamRole.MANAGER,
        ).all()
        managed_team_ids = [m[0] for m in managed_memberships]

        if not managed_team_ids:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="Not enough permissions to access audit logs",
            )

        # Team managers only see logs associated with their managed teams
        query = db.query(AuditLog).filter(AuditLog.team_id.in_(managed_team_ids))

    # ─── Database-side Filtering ──────────────────────────────────────────────
    if action is not None:
        query = query.filter(AuditLog.action == action)
    if entity_type is not None:
        query = query.filter(AuditLog.entity_type == entity_type)
    if actor_id is not None:
        query = query.filter(AuditLog.actor_id == actor_id)
    if entity_id is not None:
        query = query.filter(AuditLog.entity_id == entity_id)
    if date_from is not None:
        query = query.filter(AuditLog.created_at >= date_from)
    if date_to is not None:
        query = query.filter(AuditLog.created_at <= date_to)

    # ─── Deterministic Default Ordering ───────────────────────────────────────
    query = query.order_by(AuditLog.created_at.desc(), AuditLog.id.desc())

    # ─── Count and Pagination ─────────────────────────────────────────────────
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
