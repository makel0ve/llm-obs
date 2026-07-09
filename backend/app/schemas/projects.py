from datetime import datetime
from typing import Literal

from pydantic import BaseModel, Field

ApiKeyScope = Literal["ingest", "read", "read_write"]
PayloadStorageMode = Literal["all", "errors", "none"]


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
