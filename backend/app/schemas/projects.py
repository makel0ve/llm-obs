from datetime import datetime
from typing import Literal

from pydantic import BaseModel, Field

ApiKeyScope = Literal["ingest", "read", "read_write"]
PayloadStorageMode = Literal["all", "errors", "none"]


class ProjectRecord(BaseModel):
    id: str
    name: str
    is_active: bool
    created_at: datetime | None = None
    retention_days: int
    payload_storage_mode: PayloadStorageMode
    payload_max_bytes: int
    payload_redact_keys: str


class ProjectCreate(BaseModel):
    name: str = Field(min_length=1, max_length=255)
    retention_days: int = Field(default=90, ge=7, le=365)
    payload_storage_mode: PayloadStorageMode = "all"
    payload_max_bytes: int = Field(default=262144, ge=0, le=10 * 1024 * 1024)
    payload_redact_keys: str = Field(
        default="api_key,password,secret,token,authorization", max_length=1000
    )


class ProjectCreateResponse(ProjectRecord):
    api_key: str
    note: str


class ProjectSettings(BaseModel):
    retention_days: int
    payload_storage_mode: PayloadStorageMode
    payload_max_bytes: int
    payload_redact_keys: str


class ProjectSettingsUpdate(BaseModel):
    retention_days: int | None = Field(default=None, ge=7, le=365)
    payload_storage_mode: PayloadStorageMode | None = None
    payload_max_bytes: int | None = Field(default=None, ge=0, le=10 * 1024 * 1024)
    payload_redact_keys: str | None = Field(default=None, max_length=1000)


class ProjectApiKeyCreate(BaseModel):
    name: str = Field(min_length=1, max_length=100)
    description: str | None = Field(default=None, max_length=500)
    scope: ApiKeyScope = "ingest"


class ProjectApiKeyRecord(BaseModel):
    id: str
    name: str
    description: str | None = None
    scope: ApiKeyScope
    is_active: bool
    created_at: datetime | None = None
    last_used_at: datetime | None = None
    revoked_at: datetime | None = None


class ProjectApiKeyCreateResponse(ProjectApiKeyRecord):
    api_key: str
