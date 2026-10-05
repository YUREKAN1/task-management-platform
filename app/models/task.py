from sqlalchemy import Column, String, DateTime, ForeignKey, Enum
from sqlalchemy import Uuid as UUID
from sqlalchemy.orm import relationship
import uuid
from datetime import datetime, timezone
from app.database.session import Base
from app.models.enums import TaskStatus, TaskPriority

class Task(Base):
    __tablename__ = "tasks"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    title = Column(String, nullable=False)
    description = Column(String, nullable=True)
    status = Column(Enum(TaskStatus), default=TaskStatus.TODO, nullable=False, index=True)
    priority = Column(Enum(TaskPriority), default=TaskPriority.MEDIUM, nullable=False, index=True)
    due_date = Column(DateTime(timezone=True), nullable=True, index=True)
    
    project_id = Column(UUID(as_uuid=True), ForeignKey("projects.id", ondelete="CASCADE"), nullable=True, index=True)
    created_by = Column(UUID(as_uuid=True), ForeignKey("users.id"), nullable=False)
    assigned_to = Column(UUID(as_uuid=True), ForeignKey("users.id"), nullable=True, index=True)
    
    created_at = Column(DateTime(timezone=True), default=lambda: datetime.now(timezone.utc), nullable=False)
    updated_at = Column(DateTime(timezone=True), default=lambda: datetime.now(timezone.utc), onupdate=lambda: datetime.now(timezone.utc), nullable=False)
    completed_at = Column(DateTime(timezone=True), nullable=True)

    project = relationship("Project", back_populates="tasks")
    creator = relationship("User", back_populates="created_tasks", foreign_keys=[created_by])
    assignee = relationship("User", back_populates="assigned_tasks", foreign_keys=[assigned_to])
    
    tags = relationship("Tag", secondary="task_tags", back_populates="tasks")
