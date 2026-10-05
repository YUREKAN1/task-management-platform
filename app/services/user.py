from sqlalchemy.orm import Session
from fastapi import HTTPException, status
from app.schemas.user import UserUpdate
from app.models.user import User
from app.models.enums import AuditAction
from app.services.audit import create_audit_log

def update_user_profile(db: Session, user: User, user_in: UserUpdate) -> User:
    changes = {}
    if user_in.email and user_in.email != user.email:
        # Check if email is taken
        existing_user = db.query(User).filter(User.email == user_in.email).first()
        if existing_user:
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail="Email already registered",
            )
        user.email = user_in.email
        changes["email"] = user.email
    if user_in.name and user_in.name != user.name:
        user.name = user_in.name
        changes["name"] = user.name
    
    create_audit_log(
        db=db,
        actor_id=user.id,
        action=AuditAction.USER_UPDATED,
        entity_type="user",
        entity_id=user.id,
        description="User profile updated",
        metadata=changes,
    )
    db.commit()
    db.refresh(user)
    return user

def deactivate_user(db: Session, user: User, actor: User) -> User:
    user.is_active = False
    create_audit_log(
        db=db,
        actor_id=actor.id,
        action=AuditAction.USER_DEACTIVATED,
        entity_type="user",
        entity_id=user.id,
        description=f"User {user.email} deactivated",
        metadata={"user_id": str(user.id)},
    )
    db.commit()
    db.refresh(user)
    return user
