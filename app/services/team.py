from sqlalchemy.orm import Session
from fastapi import HTTPException, status
from app.models.team import Team, TeamMember
from app.models.user import User
from app.models.enums import TeamRole, AuditAction
from app.schemas.team import TeamCreate, TeamMemberCreate, TeamMemberUpdate
from app.services.audit import create_audit_log
from uuid import UUID

def get_team_or_404(db: Session, team_id: UUID) -> Team:
    team = db.query(Team).filter(Team.id == team_id).first()
    if not team:
        raise HTTPException(status_code=404, detail="Team not found")
    return team

def require_team_member(db: Session, team_id: UUID, user_id: UUID) -> TeamMember:
    member = db.query(TeamMember).filter(TeamMember.team_id == team_id, TeamMember.user_id == user_id).first()
    if not member:
        raise HTTPException(status_code=403, detail="Not enough permissions (must be a team member)")
    return member

def require_team_manager(db: Session, team_id: UUID, user_id: UUID) -> TeamMember:
    member = require_team_member(db, team_id, user_id)
    if member.role != TeamRole.MANAGER:
        raise HTTPException(status_code=403, detail="Not enough permissions (must be a team manager)")
    return member

def create_team(db: Session, team_in: TeamCreate, user: User) -> Team:
    db_team = Team(
        name=team_in.name,
        description=team_in.description,
        created_by=user.id
    )
    db.add(db_team)
    db.flush() # flush to get team id for membership
    
    db_member = TeamMember(
        team_id=db_team.id,
        user_id=user.id,
        role=TeamRole.MANAGER
    )
    db.add(db_member)
    
    create_audit_log(
        db=db,
        actor_id=user.id,
        action=AuditAction.TEAM_CREATED,
        entity_type="team",
        entity_id=db_team.id,
        team_id=db_team.id,
        description=f"Team '{db_team.name}' created",
        metadata={"name": db_team.name},
    )
    
    db.commit()
    db.refresh(db_team)
    return db_team

def get_user_teams(db: Session, user: User):
    # Returns teams with user_role annotated
    memberships = db.query(TeamMember).filter(TeamMember.user_id == user.id).all()
    results = []
    for m in memberships:
        team_info = m.team.__dict__.copy()
        team_info['user_role'] = m.role
        results.append(team_info)
    return results

def get_team(db: Session, team_id: UUID, user: User) -> Team:
    team = get_team_or_404(db, team_id)
    require_team_member(db, team_id, user.id)
    return team

def get_team_members(db: Session, team_id: UUID, user: User):
    get_team_or_404(db, team_id)
    require_team_member(db, team_id, user.id)
    memberships = db.query(TeamMember).filter(TeamMember.team_id == team_id).all()
    results = []
    for m in memberships:
        results.append({
            "user_id": m.user.id,
            "name": m.user.name,
            "email": m.user.email,
            "role": m.role,
            "joined_at": m.joined_at
        })
    return results

def add_team_member(db: Session, team_id: UUID, member_in: TeamMemberCreate, current_user: User):
    get_team_or_404(db, team_id)
    require_team_manager(db, team_id, current_user.id)
    
    target_user = db.query(User).filter(User.email == member_in.email).first()
    if not target_user:
        raise HTTPException(status_code=404, detail="User not found")
    if not target_user.is_active or target_user.deleted_at is not None:
        raise HTTPException(status_code=400, detail="User is inactive")
        
    existing_member = db.query(TeamMember).filter(TeamMember.team_id == team_id, TeamMember.user_id == target_user.id).first()
    if existing_member:
        raise HTTPException(status_code=409, detail="User is already a member of this team")
        
    new_member = TeamMember(
        team_id=team_id,
        user_id=target_user.id,
        role=member_in.role
    )
    db.add(new_member)
    db.flush()
    
    create_audit_log(
        db=db,
        actor_id=current_user.id,
        action=AuditAction.MEMBER_ADDED,
        entity_type="team",
        entity_id=team_id,
        team_id=team_id,
        description=f"User {target_user.email} added to team as {member_in.role.value if hasattr(member_in.role, 'value') else str(member_in.role)}",
        metadata={"user_id": str(target_user.id), "email": target_user.email, "role": member_in.role.value if hasattr(member_in.role, "value") else str(member_in.role)},
    )
    
    db.commit()
    return {
        "user_id": target_user.id,
        "name": target_user.name,
        "email": target_user.email,
        "role": new_member.role,
        "joined_at": new_member.joined_at
    }

def remove_team_member(db: Session, team_id: UUID, target_user_id: UUID, current_user: User):
    get_team_or_404(db, team_id)
    require_team_manager(db, team_id, current_user.id)
    
    target_member = db.query(TeamMember).filter(TeamMember.team_id == team_id, TeamMember.user_id == target_user_id).first()
    if not target_member:
        raise HTTPException(status_code=404, detail="Membership not found")
        
    if target_member.role == TeamRole.MANAGER:
        manager_count = db.query(TeamMember).filter(TeamMember.team_id == team_id, TeamMember.role == TeamRole.MANAGER).count()
        if manager_count <= 1:
            raise HTTPException(status_code=400, detail="Cannot remove the last manager of the team")
            
    create_audit_log(
        db=db,
        actor_id=current_user.id,
        action=AuditAction.MEMBER_REMOVED,
        entity_type="team",
        entity_id=team_id,
        team_id=team_id,
        description=f"User {target_user_id} removed from team",
        metadata={"user_id": str(target_user_id)},
    )
    
    db.delete(target_member)
    db.commit()

def update_team_member_role(db: Session, team_id: UUID, target_user_id: UUID, role_in: TeamMemberUpdate, current_user: User):
    get_team_or_404(db, team_id)
    require_team_manager(db, team_id, current_user.id)
    
    target_member = db.query(TeamMember).filter(TeamMember.team_id == team_id, TeamMember.user_id == target_user_id).first()
    if not target_member:
        raise HTTPException(status_code=404, detail="Membership not found")
        
    if target_member.role == TeamRole.MANAGER and role_in.role == TeamRole.MEMBER:
        manager_count = db.query(TeamMember).filter(TeamMember.team_id == team_id, TeamMember.role == TeamRole.MANAGER).count()
        if manager_count <= 1:
            raise HTTPException(status_code=400, detail="Cannot demote the last manager of the team")
            
    old_role = target_member.role
    target_member.role = role_in.role
    
    create_audit_log(
        db=db,
        actor_id=current_user.id,
        action=AuditAction.MEMBER_ROLE_CHANGED,
        entity_type="team",
        entity_id=team_id,
        team_id=team_id,
        description=f"User {target_user_id} role changed from {old_role.value if hasattr(old_role, 'value') else str(old_role)} to {role_in.role.value if hasattr(role_in.role, 'value') else str(role_in.role)}",
        metadata={
            "user_id": str(target_user_id),
            "old_role": old_role.value if hasattr(old_role, "value") else str(old_role),
            "new_role": role_in.role.value if hasattr(role_in.role, "value") else str(role_in.role),
        },
    )
    
    db.commit()
    db.refresh(target_member)
    return {
        "user_id": target_member.user.id,
        "name": target_member.user.name,
        "email": target_member.user.email,
        "role": target_member.role,
        "joined_at": target_member.joined_at
    }
