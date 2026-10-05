from pydantic import BaseModel, ConfigDict, Field
from typing import Optional
from uuid import UUID
from datetime import datetime

class ProjectBase(BaseModel):
    name: str = Field(..., min_length=1, description="Name of the project")
    description: Optional[str] = Field(None, description="Optional project description")

class ProjectCreate(ProjectBase):
    pass

class ProjectUpdate(BaseModel):
    name: Optional[str] = Field(None, min_length=1, description="New name for the project")
    description: Optional[str] = Field(None, description="New description for the project")

class ProjectResponse(ProjectBase):
    id: UUID
    team_id: UUID = Field(..., description="UUID of the parent team that owns this project")
    created_by: UUID = Field(..., description="UUID of the user who created this project")
    created_at: datetime
    updated_at: datetime

    model_config = ConfigDict(from_attributes=True)
