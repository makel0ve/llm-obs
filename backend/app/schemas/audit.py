from datetime import datetime
from typing import Any

from pydantic import BaseModel


class AuditLogEvent(BaseModel):
    id: int
    action: str
    user_id: str | None = None
    user_email: str | None = None
    resource_id: str | None = None
    metadata: dict[str, Any]
    created_at: datetime


class AuditLogResponse(BaseModel):
    events: list[AuditLogEvent]
    next_cursor: str | None = None
