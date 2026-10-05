from sqlalchemy import Column, String, DateTime, ForeignKey, Enum, JSON
from sqlalchemy import Uuid as UUID
from sqlalchemy.orm import relationship
import uuid
from datetime import datetime, timezone
from app.database.session import Base
from app.models.enums import AuditAction

class AuditLog(Base):
    __tablename__ = "audit_logs"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    actor_id = Column(UUID(as_uuid=True), ForeignKey("users.id"), nullable=False, index=True)
    action = Column(Enum(AuditAction), nullable=False, index=True)
    entity_type = Column(String, nullable=False, index=True)
    entity_id = Column(UUID(as_uuid=True), nullable=False, index=True)
    team_id = Column(UUID(as_uuid=True), ForeignKey("teams.id", ondelete="SET NULL"), nullable=True, index=True)
    description = Column(String, nullable=True)
    metadata_ = Column("metadata", JSON, nullable=True)

    created_at = Column(DateTime(timezone=True), default=lambda: datetime.now(timezone.utc), nullable=False, index=True)

    actor = relationship("User", foreign_keys=[actor_id])
    team = relationship("Team", foreign_keys=[team_id])
