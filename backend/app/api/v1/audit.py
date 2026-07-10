import json
from datetime import datetime
from typing import Any

from fastapi import APIRouter, Depends, Query
from sqlalchemy import text

from app.core.auth import get_current_user
from app.core.db import get_db
from app.core.rbac import require_admin
from app.schemas.audit import AuditLogEvent, AuditLogResponse

router = APIRouter(prefix="/v1/audit", tags=["audit"])


def parse_metadata(value: Any) -> dict[str, Any]:
    if isinstance(value, dict):
        return value
    if isinstance(value, str):
        try:
            parsed = json.loads(value)
            return parsed if isinstance(parsed, dict) else {}
        except json.JSONDecodeError:
            return {}
    return {}


@router.get("/events", response_model=AuditLogResponse)
async def list_audit_events(
    action: str | None = Query(default=None, max_length=100),
    user_id: str | None = Query(default=None),
    from_dt: datetime | None = Query(default=None),
    to_dt: datetime | None = Query(default=None),
    cursor: int | None = Query(default=None, ge=1),
    page_size: int = Query(default=50, ge=1, le=100),
    user: dict[str, Any] = Depends(get_current_user),
) -> AuditLogResponse:
    require_admin(user)

    async with get_db() as db:
        result = await db.execute(
            text(
                """
                SELECT audit_log.id, audit_log.action, audit_log.user_id,
                    users.email AS user_email, audit_log.resource_id,
                    audit_log.metadata, audit_log.created_at
                FROM audit_log
                LEFT JOIN users ON users.id = audit_log.user_id
                WHERE audit_log.org_id = :org
                    AND (
                        CAST(:action AS varchar) IS NULL
                        OR audit_log.action ILIKE CAST(:action AS varchar)
                    )
                    AND (
                        CAST(:user_id AS uuid) IS NULL
                        OR audit_log.user_id = CAST(:user_id AS uuid)
                    )
                    AND (
                        CAST(:from_dt AS timestamptz) IS NULL
                        OR audit_log.created_at >= CAST(:from_dt AS timestamptz)
                    )
                    AND (
                        CAST(:to_dt AS timestamptz) IS NULL
                        OR audit_log.created_at <= CAST(:to_dt AS timestamptz)
                    )
                    AND (
                        CAST(:cursor AS bigint) IS NULL
                        OR audit_log.id < CAST(:cursor AS bigint)
                    )
                ORDER BY audit_log.id DESC
                LIMIT :limit
                """
            ),
            {
                "org": user["org_id"],
                "action": f"%{action.strip()}%" if action and action.strip() else None,
                "user_id": user_id,
                "from_dt": from_dt,
                "to_dt": to_dt,
                "cursor": cursor,
                "limit": page_size + 1,
            },
        )

    rows = result.mappings().all()
    page = rows[:page_size]
    next_cursor = str(page[-1]["id"]) if len(rows) > page_size and page else None

    return AuditLogResponse(
        events=[
            AuditLogEvent(
                id=row["id"],
                action=row["action"],
                user_id=str(row["user_id"]) if row["user_id"] else None,
                user_email=row["user_email"],
                resource_id=str(row["resource_id"]) if row["resource_id"] else None,
                metadata=parse_metadata(row["metadata"]),
                created_at=row["created_at"],
            )
            for row in page
        ],
        next_cursor=next_cursor,
    )
