from datetime import datetime
from typing import Literal

from pydantic import BaseModel, EmailStr, Field, model_validator

UserRole = Literal["admin", "member", "viewer"]
ProjectMembershipRole = Literal["member", "viewer"]


class OrganizationUser(BaseModel):
    id: str
    email: EmailStr
    role: UserRole
    is_active: bool
    created_at: datetime | None = None


class UserCreate(BaseModel):
    email: EmailStr
    role: UserRole = "member"


class UserRoleUpdate(BaseModel):
    role: UserRole


class UserProjectAssignment(BaseModel):
    project_id: str
    role: ProjectMembershipRole = "viewer"


class UserInviteCreate(BaseModel):
    email: EmailStr
    role: UserRole = "member"
    project_assignments: list[UserProjectAssignment] = Field(default_factory=list)

    @model_validator(mode="after")
    def validate_unique_project_assignments(self) -> "UserInviteCreate":
        project_ids = [assignment.project_id for assignment in self.project_assignments]
        if len(project_ids) != len(set(project_ids)):
            raise ValueError("Project assignments must be unique")
        return self


class UserInviteResponse(BaseModel):
    id: str
    email: EmailStr
    role: UserRole
    project_assignments: list[UserProjectAssignment] = Field(default_factory=list)
    invite_token: str
    expires_at: datetime


class UserProjectAccessRecord(BaseModel):
    project_id: str
    project_name: str
    project_role: UserRole | None = None
    is_active: bool
    retention_days: int


class UserInviteAccept(BaseModel):
    token: str = Field(min_length=32)
    password: str = Field(min_length=8, max_length=128)
