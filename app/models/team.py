from sqlalchemy import Column, String, DateTime, ForeignKey, UniqueConstraint, Enum
from sqlalchemy import Uuid as UUID
from sqlalchemy.orm import relationship
import uuid
from datetime import datetime, timezone
from app.database.session import Base
from app.models.enums import TeamRole

class Team(Base):
    __tablename__ = "teams"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    name = Column(String, nullable=False)
    description = Column(String, nullable=True)
    created_by = Column(UUID(as_uuid=True), ForeignKey("users.id"), nullable=False)
    
    created_at = Column(DateTime(timezone=True), default=lambda: datetime.now(timezone.utc), nullable=False)
    updated_at = Column(DateTime(timezone=True), default=lambda: datetime.now(timezone.utc), onupdate=lambda: datetime.now(timezone.utc), nullable=False)

    creator = relationship("User", back_populates="created_teams", foreign_keys=[created_by])
    members = relationship("TeamMember", back_populates="team", cascade="all, delete-orphan")
    projects = relationship("Project", back_populates="team")

class TeamMember(Base):
    __tablename__ = "team_members"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    team_id = Column(UUID(as_uuid=True), ForeignKey("teams.id", ondelete="CASCADE"), nullable=False)
    user_id = Column(UUID(as_uuid=True), ForeignKey("users.id", ondelete="CASCADE"), nullable=False)
    role = Column(Enum(TeamRole), default=TeamRole.MEMBER, nullable=False)
    joined_at = Column(DateTime(timezone=True), default=lambda: datetime.now(timezone.utc), nullable=False)

    __table_args__ = (
        UniqueConstraint("team_id", "user_id", name="uq_team_user"),
    )

    team = relationship("Team", back_populates="members")
    user = relationship("User", back_populates="team_memberships")
