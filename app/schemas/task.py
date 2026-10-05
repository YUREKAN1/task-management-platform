from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator
from typing import Optional
from uuid import UUID
from datetime import datetime
from app.models.enums import TaskStatus, TaskPriority


class TaskCreate(BaseModel):
    """Schema for creating a personal task (no project)."""
    title: str = Field(..., min_length=1, description="Title of the task")
    description: Optional[str] = Field(None, description="Optional detailed description")
    priority: TaskPriority = Field(TaskPriority.MEDIUM, description="Priority level (LOW, MEDIUM, HIGH)")
    due_date: Optional[datetime] = Field(None, description="Optional target completion timestamp (UTC)")


class ProjectTaskCreate(BaseModel):
    """Schema for creating a project task via POST /projects/{project_id}/tasks."""
    title: str = Field(..., min_length=1, description="Title of the project task")
    description: Optional[str] = Field(None, description="Optional detailed description")
    priority: TaskPriority = Field(TaskPriority.MEDIUM, description="Priority level (LOW, MEDIUM, HIGH)")
    due_date: Optional[datetime] = Field(None, description="Optional target completion timestamp (UTC)")
    assigned_to: Optional[UUID] = Field(None, description="Optional UUID of a team member to assign")


class TaskUpdate(BaseModel):
    """Schema for PATCH /tasks/{task_id}. All fields optional."""
    title: Optional[str] = Field(None, min_length=1, description="New title for the task")
    description: Optional[str] = Field(None, description="New description for the task")
    status: Optional[TaskStatus] = Field(None, description="New status (TODO, IN_PROGRESS, COMPLETED)")
    priority: Optional[TaskPriority] = Field(None, description="New priority (LOW, MEDIUM, HIGH)")
    due_date: Optional[datetime] = Field(None, description="New due date timestamp (UTC)")


class TaskAssignmentUpdate(BaseModel):
    """Schema for PATCH /tasks/{task_id}/assignment."""
    assigned_to: Optional[UUID] = Field(
        None,
        description="UUID of the team member to assign, or null to unassign the task",
    )


class TaskResponse(BaseModel):
    id: UUID
    title: str
    description: Optional[str] = None
    status: TaskStatus
    priority: TaskPriority
    due_date: Optional[datetime] = None
    project_id: Optional[UUID] = Field(None, description="UUID of the parent project, or null for personal tasks")
    created_by: UUID = Field(..., description="UUID of the user who created this task")
    assigned_to: Optional[UUID] = Field(None, description="UUID of the user currently assigned to this task")
    created_at: datetime
    updated_at: datetime
    completed_at: Optional[datetime] = Field(
        None,
        description="UTC timestamp automatically set when the task is COMPLETED and cleared when the task is reopened.",
    )

    model_config = ConfigDict(from_attributes=True)


class PaginatedTaskResponse(BaseModel):
    items: list[TaskResponse]
    page: int = Field(..., description="Current page number (1-based)")
    page_size: int = Field(..., description="Number of items per page")
    total: int = Field(..., description="Total number of items matching filters across all pages")
    total_pages: int = Field(..., description="Total number of available pages")

    model_config = ConfigDict(from_attributes=True)
