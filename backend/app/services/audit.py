import json

import structlog
from sqlalchemy import text

from app.core.db import get_db

log = structlog.get_logger()


async def log_audit(
    org_id: str,
    action: str,
    user_id: str | None = None,
    resource_id: str | None = None,
    metadata: dict | None = None,
) -> None:
    try:
        async with get_db() as db:
            await db.execute(
                text(
                    """
                INSERT INTO audit_log (org_id, user_id, action, resource_id, metadata)
                VALUES (:org, :user, :action, :resource, :meta)
                """
                ),
                {
                    "org": org_id,
                    "user": user_id,
                    "action": action,
                    "resource": resource_id,
                    "meta": json.dumps(metadata or {}),
                },
            )
            await db.commit()

    except Exception as e:
        log.error("audit_log_failed", action=action, org_id=org_id, error=str(e))
