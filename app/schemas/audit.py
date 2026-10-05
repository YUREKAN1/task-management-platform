from pydantic import BaseModel, ConfigDict, Field, AliasChoices
from typing import Optional, Any
from uuid import UUID
from datetime import datetime
from app.models.enums import AuditAction

class AuditLogResponse(BaseModel):
    id: UUID
    actor_id: UUID = Field(..., description="UUID of the user who performed the action")
    action: AuditAction = Field(..., description="Action performed (e.g. USER_REGISTERED, TASK_CREATED, etc.)")
    entity_type: str = Field(..., description="Category of entity affected (user, team, project, task)")
    entity_id: UUID = Field(..., description="UUID of the entity affected by the action")
    team_id: Optional[UUID] = Field(None, description="UUID of the associated team, or null for user/personal entities")
    description: Optional[str] = Field(None, description="Human-readable summary of the logged event")
    metadata: Optional[Any] = Field(
        None,
        validation_alias=AliasChoices("metadata_", "metadata"),
        description="Structured JSON payload capturing event metadata (e.g. state changes, modified fields, target entity identifiers).",
    )
    created_at: datetime = Field(..., description="UTC timestamp when the audit log was recorded")

    model_config = ConfigDict(from_attributes=True, populate_by_name=True)


class PaginatedAuditLogResponse(BaseModel):
    items: list[AuditLogResponse]
    page: int = Field(..., description="Current page number (1-based)")
    page_size: int = Field(..., description="Number of items per page")
    total: int = Field(..., description="Total number of audit logs matching query filters")
    total_pages: int = Field(..., description="Total number of available pages")

    model_config = ConfigDict(from_attributes=True)
