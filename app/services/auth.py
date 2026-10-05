from sqlalchemy.orm import Session
from app.schemas.user import UserCreate
from app.models.user import User
from app.core.security import get_password_hash, verify_password

from app.models.enums import AuditAction
from app.services.audit import create_audit_log

def get_user_by_email(db: Session, email: str) -> User | None:
    return db.query(User).filter(User.email == email).first()

def create_user(db: Session, user_in: UserCreate) -> User:
    hashed_password = get_password_hash(user_in.password)
    db_user = User(
        name=user_in.name,
        email=user_in.email,
        password_hash=hashed_password,
    )
    db.add(db_user)
    db.flush()
    create_audit_log(
        db=db,
        actor_id=db_user.id,
        action=AuditAction.USER_REGISTERED,
        entity_type="user",
        entity_id=db_user.id,
        description=f"User {db_user.email} registered",
        metadata={"email": db_user.email, "name": db_user.name},
    )
    db.commit()
    db.refresh(db_user)
    return db_user

def authenticate_user(db: Session, email: str, password: str) -> User | None:
    user = get_user_by_email(db, email=email)
    if not user:
        return None
    if not verify_password(password, user.password_hash):
        return None
    return user
