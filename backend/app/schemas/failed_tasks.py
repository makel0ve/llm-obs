from datetime import datetime
from typing import Any

from pydantic import BaseModel, Field


class FailedTaskResponse(BaseModel):
    id: int
    task_name: str
    project_id: str | None = None
    task_args: dict[str, Any] | None = None
    error: str | None = None
    attempts: int | None = None
    failed_at: datetime
    resolved: bool


class FailedTaskResolveResponse(BaseModel):
    resolved: bool = Field(default=True)


class FailedTaskRetryResponse(BaseModel):
    retried: bool = Field(default=True)
