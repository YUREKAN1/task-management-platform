from datetime import datetime
from typing import Optional
from uuid import UUID
from fastapi import APIRouter, Depends, Query
from sqlalchemy.orm import Session

from app.api.deps import get_db, get_current_user
from app.models.enums import AuditAction
from app.models.user import User
from app.schemas.audit import PaginatedAuditLogResponse
from app.services import audit as audit_service

router = APIRouter()


@router.get(
    "/audit-logs",
    response_model=PaginatedAuditLogResponse,
    summary="Query Audit Logs",
    responses={
        200: {"description": "Paginated audit log entries matching query filters."},
        401: {"description": "Missing, invalid, or expired JWT Bearer token."},
        403: {"description": "Caller lacks required privileges (only global ADMIN or team MANAGER can view audit logs)."},
        422: {"description": "Invalid query parameters or date formats."},
    },
)
def get_audit_logs(
    page: int = Query(1, ge=1, description="Page number (>= 1)"),
    page_size: int = Query(20, ge=1, le=100, description="Items per page (1 to 100)"),
    action: Optional[AuditAction] = Query(None, description="Filter by audit action"),
    entity_type: Optional[str] = Query(None, description="Filter by entity type (user, team, project, task)"),
    actor_id: Optional[UUID] = Query(None, description="Filter by actor user UUID"),
    entity_id: Optional[UUID] = Query(None, description="Filter by target entity UUID"),
    date_from: Optional[datetime] = Query(None, description="Filter records created on or after this timestamp"),
    date_to: Optional[datetime] = Query(None, description="Filter records created on or before this timestamp"),
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """
    Queries platform audit log entries.
    - Global `ADMIN`: Accesses all system audit logs across all teams and users.
    - Team `MANAGER`: Accesses audit logs scoped strictly to the teams they manage (`team_id in managed_teams`).
    - Standard `USER`: Access is forbidden (returns HTTP 403 Forbidden).
    - Supports multi-field filtering by action type, entity type/ID, actor, and date ranges.
    """
    return audit_service.list_audit_logs(
        db=db,
        user=current_user,
        page=page,
        page_size=page_size,
        action=action,
        entity_type=entity_type,
        actor_id=actor_id,
        entity_id=entity_id,
        date_from=date_from,
        date_to=date_to,
    )
