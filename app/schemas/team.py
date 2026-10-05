from pydantic import BaseModel, ConfigDict, EmailStr, Field
from typing import Optional, List
from uuid import UUID
from datetime import datetime
from app.models.enums import TeamRole

class TeamBase(BaseModel):
    name: str = Field(..., min_length=1, description="Name of the team")
    description: Optional[str] = Field(None, description="Optional team description")

class TeamCreate(TeamBase):
    pass

class TeamResponse(TeamBase):
    id: UUID
    created_by: UUID
    created_at: datetime
    updated_at: datetime

    model_config = ConfigDict(from_attributes=True)

class TeamListResponse(TeamResponse):
    user_role: Optional[TeamRole] = Field(
        None,
        description="Role of the authenticated user within this team (MANAGER or MEMBER)",
    )

class TeamMemberCreate(BaseModel):
    email: EmailStr = Field(..., description="Email address of the registered user to add to the team")
    role: TeamRole = Field(..., description="Role to assign within the team (MEMBER or MANAGER)")

class TeamMemberUpdate(BaseModel):
    role: TeamRole = Field(..., description="New role for the team member (MEMBER or MANAGER)")

class TeamMemberResponse(BaseModel):
    user_id: UUID
    name: str
    email: EmailStr
    role: TeamRole
    joined_at: datetime

    model_config = ConfigDict(from_attributes=True)
