from pydantic import BaseModel, ConfigDict, EmailStr, Field, field_validator
from typing import Optional
from uuid import UUID
from datetime import datetime
from app.models.enums import GlobalRole

class UserBase(BaseModel):
    name: str = Field(..., min_length=1)
    email: EmailStr

    @field_validator("email", mode="before")
    def lowercase_email(cls, v: str) -> str:
        if isinstance(v, str):
            return v.strip().lower()
        return v

class UserCreate(UserBase):
    password: str = Field(..., min_length=1)

class UserLogin(BaseModel):
    email: EmailStr
    password: str

    @field_validator("email", mode="before")
    def lowercase_email(cls, v: str) -> str:
        if isinstance(v, str):
            return v.strip().lower()
        return v

class UserUpdate(BaseModel):
    name: Optional[str] = Field(None, min_length=1)
    email: Optional[EmailStr] = None

    @field_validator("email", mode="before")
    def lowercase_email(cls, v: str) -> str:
        if isinstance(v, str):
            return v.strip().lower()
        return v

class UserResponse(UserBase):
    id: UUID
    global_role: GlobalRole
    is_active: bool
    created_at: datetime
    updated_at: datetime

    model_config = ConfigDict(from_attributes=True)
