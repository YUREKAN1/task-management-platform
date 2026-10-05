from sqlalchemy import Column, String, DateTime, ForeignKey
from sqlalchemy import Uuid as UUID
from sqlalchemy.orm import relationship, validates
import uuid
from datetime import datetime, timezone
from app.database.session import Base

class TaskTag(Base):
    __tablename__ = "task_tags"

    task_id = Column(UUID(as_uuid=True), ForeignKey("tasks.id", ondelete="CASCADE"), primary_key=True)
    tag_id = Column(UUID(as_uuid=True), ForeignKey("tags.id", ondelete="CASCADE"), primary_key=True)

class Tag(Base):
    __tablename__ = "tags"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    name = Column(String, unique=True, index=True, nullable=False)
    created_at = Column(DateTime(timezone=True), default=lambda: datetime.now(timezone.utc), nullable=False)

    tasks = relationship("Task", secondary="task_tags", back_populates="tags")

    @validates("name")
    def validate_name(self, key, name):
        if name:
            return name.strip().lower()
        return name
