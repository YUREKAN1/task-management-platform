import re
from sqlalchemy import Column, String, Boolean, DateTime, Enum
from sqlalchemy import Uuid as UUID
from sqlalchemy.orm import relationship, validates
import uuid
from datetime import datetime, timezone
from app.database.session import Base
from app.models.enums import GlobalRole

class User(Base):
    __tablename__ = "users"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4, index=True)
    name = Column(String, nullable=False)
    email = Column(String, unique=True, index=True, nullable=False)
    password_hash = Column(String, nullable=False)
    global_role = Column(Enum(GlobalRole), default=GlobalRole.USER, nullable=False)
    is_active = Column(Boolean, default=True, nullable=False)
    
    created_at = Column(DateTime(timezone=True), default=lambda: datetime.now(timezone.utc), nullable=False)
    updated_at = Column(DateTime(timezone=True), default=lambda: datetime.now(timezone.utc), onupdate=lambda: datetime.now(timezone.utc), nullable=False)
    deleted_at = Column(DateTime(timezone=True), nullable=True)

    # Relationships
    created_teams = relationship("Team", back_populates="creator", foreign_keys="[Team.created_by]")
    team_memberships = relationship("TeamMember", back_populates="user")
    created_projects = relationship("Project", back_populates="creator", foreign_keys="[Project.created_by]")
    created_tasks = relationship("Task", back_populates="creator", foreign_keys="[Task.created_by]")
    assigned_tasks = relationship("Task", back_populates="assignee", foreign_keys="[Task.assigned_to]")

    @validates("email")
    def validate_email(self, key, address):
        if address:
            return address.strip().lower()
        return address
