from pydantic import BaseModel, EmailStr, Field


class RegisterRequest(BaseModel):
    email: EmailStr
    password: str = Field(min_length=8, max_length=128)
    org_name: str = Field(min_length=2, max_length=100)
    bootstrap_token: str | None = Field(default=None, min_length=1, max_length=512)


class LoginRequest(BaseModel):
    email: EmailStr
    password: str


class TokenResponse(BaseModel):
    access_token: str
    token_type: str
    role: str


class RegisterResponse(TokenResponse):
    api_key: str
    project_id: str


class LoginResponse(TokenResponse):
    project_id: str | None
