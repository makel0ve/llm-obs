from datetime import datetime
from typing import Literal

from pydantic import BaseModel, EmailStr, Field

UserRole = Literal["admin", "member", "viewer"]


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


class UserInviteCreate(BaseModel):
    email: EmailStr
    role: UserRole = "member"


class UserInviteResponse(BaseModel):
    id: str
    email: EmailStr
    role: UserRole
    invite_token: str
    expires_at: datetime


class UserInviteAccept(BaseModel):
    token: str = Field(min_length=32)
    password: str = Field(min_length=8, max_length=128)
