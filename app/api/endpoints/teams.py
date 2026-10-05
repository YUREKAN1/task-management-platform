from fastapi import APIRouter, Depends, Path, status
from sqlalchemy.orm import Session
from typing import List
from uuid import UUID
from app.api.deps import get_db, get_current_user
from app.schemas.team import TeamCreate, TeamResponse, TeamListResponse, TeamMemberCreate, TeamMemberUpdate, TeamMemberResponse
from app.services import team as team_service
from app.models.user import User

router = APIRouter()

@router.post(
    "",
    response_model=TeamResponse,
    status_code=status.HTTP_201_CREATED,
    summary="Create New Team",
    responses={
        201: {"description": "Team created successfully. Creator is automatically assigned MANAGER role."},
        401: {"description": "Missing, invalid, or expired JWT Bearer token."},
        422: {"description": "Validation error (e.g. empty team name)."},
    },
)
def create_team(
    team_in: TeamCreate,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    """
    Creates a new team workspace. The creating user is automatically enrolled as the initial `MANAGER`.
    Records a `TEAM_CREATED` audit event.
    """
    return team_service.create_team(db, team_in=team_in, user=current_user)

@router.get(
    "",
    response_model=List[TeamListResponse],
    summary="List User Teams",
    responses={
        200: {"description": "List of teams the authenticated user belongs to, including their team role."},
        401: {"description": "Missing, invalid, or expired JWT Bearer token."},
    },
)
def get_user_teams(
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    """
    Lists all teams in which the current authenticated user holds active membership.
    Each item includes the caller's specific `user_role` (`MANAGER` or `MEMBER`).
    """
    return team_service.get_user_teams(db, user=current_user)

@router.get(
    "/{team_id}",
    response_model=TeamResponse,
    summary="Get Team Details",
    responses={
        200: {"description": "Team details retrieved successfully."},
        401: {"description": "Missing, invalid, or expired JWT Bearer token."},
        403: {"description": "User is not a member of this team."},
        404: {"description": "Team not found."},
        422: {"description": "Invalid UUID format."},
    },
)
def get_team(
    team_id: UUID = Path(..., description="Unique UUID identifier of the team"),
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    """
    Retrieves core details for a team. Access requires active membership within the team.
    """
    return team_service.get_team(db, team_id=team_id, user=current_user)

@router.get(
    "/{team_id}/members",
    response_model=List[TeamMemberResponse],
    summary="List Team Members",
    responses={
        200: {"description": "Roster of all active team members and their roles."},
        401: {"description": "Missing, invalid, or expired JWT Bearer token."},
        403: {"description": "User is not a member of this team."},
        404: {"description": "Team not found."},
        422: {"description": "Invalid UUID format."},
    },
)
def get_team_members(
    team_id: UUID = Path(..., description="Unique UUID identifier of the team"),
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    """
    Lists all members currently assigned to the team, including user names, emails, roles, and join dates.
    Access requires active membership within the team.
    """
    return team_service.get_team_members(db, team_id=team_id, user=current_user)

@router.post(
    "/{team_id}/members",
    response_model=TeamMemberResponse,
    status_code=status.HTTP_201_CREATED,
    summary="Add Member to Team",
    responses={
        201: {"description": "Member successfully added to the team."},
        400: {"description": "Target user account is deactivated."},
        401: {"description": "Missing, invalid, or expired JWT Bearer token."},
        403: {"description": "Caller lacks team MANAGER privileges."},
        404: {"description": "Team or target user email not found."},
        409: {"description": "User is already an active member of this team."},
        422: {"description": "Validation error in request payload or UUID format."},
    },
)
def add_team_member(
    team_id: UUID = Path(..., description="Unique UUID identifier of the team"),
    member_in: TeamMemberCreate = ...,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    """
    Adds an existing registered user to the team with role `MEMBER` or `MANAGER`.
    Requires caller to be a team `MANAGER`. Records a `MEMBER_ADDED` audit event.
    """
    return team_service.add_team_member(db, team_id=team_id, member_in=member_in, current_user=current_user)

@router.delete(
    "/{team_id}/members/{user_id}",
    status_code=status.HTTP_204_NO_CONTENT,
    summary="Remove Member from Team",
    responses={
        204: {"description": "Member successfully removed from the team."},
        400: {"description": "Cannot remove the final remaining MANAGER of the team."},
        401: {"description": "Missing, invalid, or expired JWT Bearer token."},
        403: {"description": "Caller lacks team MANAGER privileges."},
        404: {"description": "Team or member not found."},
        422: {"description": "Invalid UUID format."},
    },
)
def remove_team_member(
    team_id: UUID = Path(..., description="Unique UUID identifier of the team"),
    user_id: UUID = Path(..., description="UUID identifier of the team member to remove"),
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    """
    Removes a member from the team. Requires team `MANAGER` privileges.
    Guarded by last-manager protection (cannot remove the sole manager of a team).
    Records a `MEMBER_REMOVED` audit event.
    """
    team_service.remove_team_member(db, team_id=team_id, target_user_id=user_id, current_user=current_user)
    return None

@router.patch(
    "/{team_id}/members/{user_id}",
    response_model=TeamMemberResponse,
    summary="Update Team Member Role",
    responses={
        200: {"description": "Team member role updated successfully."},
        400: {"description": "Cannot demote the final remaining MANAGER of the team to MEMBER."},
        401: {"description": "Missing, invalid, or expired JWT Bearer token."},
        403: {"description": "Caller lacks team MANAGER privileges."},
        404: {"description": "Team or member not found."},
        422: {"description": "Validation error in request payload or UUID format."},
    },
)
def update_team_member_role(
    team_id: UUID = Path(..., description="Unique UUID identifier of the team"),
    user_id: UUID = Path(..., description="UUID identifier of the team member whose role to update"),
    role_in: TeamMemberUpdate = ...,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    """
    Promotes or demotes a team member (`MEMBER` <-> `MANAGER`).
    Requires team `MANAGER` privileges. Guarded by last-manager protection.
    Records a `MEMBER_ROLE_CHANGED` audit event.
    """
    return team_service.update_team_member_role(db, team_id=team_id, target_user_id=user_id, role_in=role_in, current_user=current_user)
