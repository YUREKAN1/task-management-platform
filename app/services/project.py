from sqlalchemy.orm import Session
from fastapi import HTTPException
from uuid import UUID
from app.models.project import Project
from app.models.user import User
from app.models.enums import GlobalRole, AuditAction
from app.schemas.project import ProjectCreate, ProjectUpdate
from app.services.team import get_team_or_404, require_team_member, require_team_manager
from app.services.audit import create_audit_log

def authorize_project_write(db: Session, team_id: UUID, user: User):
    get_team_or_404(db, team_id)
    if user.global_role == GlobalRole.ADMIN:
        return
    require_team_manager(db, team_id, user.id)

def authorize_project_read(db: Session, team_id: UUID, user: User):
    get_team_or_404(db, team_id)
    if user.global_role == GlobalRole.ADMIN:
        return
    require_team_member(db, team_id, user.id)

def get_project_or_404(db: Session, project_id: UUID) -> Project:
    project = db.query(Project).filter(Project.id == project_id).first()
    if not project:
        raise HTTPException(status_code=404, detail="Project not found")
    return project

def create_project(db: Session, team_id: UUID, project_in: ProjectCreate, user: User) -> Project:
    authorize_project_write(db, team_id, user)
    
    db_project = Project(
        name=project_in.name,
        description=project_in.description,
        team_id=team_id,
        created_by=user.id
    )
    db.add(db_project)
    db.flush()
    
    create_audit_log(
        db=db,
        actor_id=user.id,
        action=AuditAction.PROJECT_CREATED,
        entity_type="project",
        entity_id=db_project.id,
        team_id=team_id,
        description=f"Project '{db_project.name}' created",
        metadata={"name": db_project.name, "team_id": str(team_id)},
    )
    
    db.commit()
    db.refresh(db_project)
    return db_project

def list_team_projects(db: Session, team_id: UUID, user: User):
    authorize_project_read(db, team_id, user)
    return db.query(Project).filter(Project.team_id == team_id).all()

def get_project(db: Session, project_id: UUID, user: User) -> Project:
    project = get_project_or_404(db, project_id)
    authorize_project_read(db, project.team_id, user)
    return project

def update_project(db: Session, project_id: UUID, project_in: ProjectUpdate, user: User) -> Project:
    project = get_project_or_404(db, project_id)
    authorize_project_write(db, project.team_id, user)
    
    changes = {}
    if project_in.name is not None and project_in.name != project.name:
        project.name = project_in.name
        changes["name"] = project.name
    if project_in.description is not None and project_in.description != project.description:
        project.description = project_in.description
        changes["description"] = project.description
        
    create_audit_log(
        db=db,
        actor_id=user.id,
        action=AuditAction.PROJECT_UPDATED,
        entity_type="project",
        entity_id=project.id,
        team_id=project.team_id,
        description=f"Project '{project.name}' updated",
        metadata=changes,
    )
    
    db.commit()
    db.refresh(project)
    return project

def delete_project(db: Session, project_id: UUID, confirm: bool, user: User):
    if not confirm:
        raise HTTPException(status_code=400, detail="Explicit confirmation required to delete project")
        
    project = get_project_or_404(db, project_id)
    authorize_project_write(db, project.team_id, user)
    
    create_audit_log(
        db=db,
        actor_id=user.id,
        action=AuditAction.PROJECT_DELETED,
        entity_type="project",
        entity_id=project.id,
        team_id=project.team_id,
        description=f"Project '{project.name}' deleted",
        metadata={"name": project.name, "team_id": str(project.team_id)},
    )
    
    db.delete(project)
    db.commit()
