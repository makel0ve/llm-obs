import hashlib
import secrets

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import text

from app.core.auth import get_current_user
from app.core.db import get_db
from app.core.rbac import require_admin
from app.core.redis import get_redis
from app.schemas.projects import ProjectSettingsUpdate
from app.services.audit import log_audit

router = APIRouter(prefix="/v1/projects", tags=["projects"])


@router.post("/{project_id}/rotate-key")
async def rotate_api_key(project_id: str, user=Depends(get_current_user)):
    require_admin(user)

    raw_key = f"llmobs_{secrets.token_urlsafe(32)}"
    new_hash = hashlib.sha256(raw_key.encode()).hexdigest()

    async with get_db() as db:
        async with db.begin():
            current = await db.execute(
                text(
                    "SELECT api_key_hash FROM projects "
                    "WHERE id = :id AND org_id = :org FOR UPDATE"
                ),
                {"id": project_id, "org": user["org_id"]},
            )
            project = current.mappings().one_or_none()
            if not project:
                raise HTTPException(404, "Project not found")

            result = await db.execute(
                text(
                    "UPDATE projects SET api_key_hash = :hash "
                    "WHERE id = :id AND org_id = :org RETURNING id"
                ),
                {"hash": new_hash, "id": project_id, "org": user["org_id"]},
            )
            if not result.one_or_none():
                raise HTTPException(404, "Project not found")

    redis = await get_redis()
    await redis.delete(f"apikey:{project['api_key_hash']}")
    await redis.delete(f"apikey:{new_hash}")

    await log_audit(
        org_id=user["org_id"],
        user_id=user["sub"],
        action="api_key.rotate",
        resource_id=project_id,
    )

    return {"api_key": raw_key, "note": "Save this key — it won't be shown again"}


@router.patch("/{project_id}/settings")
async def update_settings(
    project_id: str, body: ProjectSettingsUpdate, user=Depends(get_current_user)
):
    require_admin(user)

    async with get_db() as db:
        result = await db.execute(
            text(
                "UPDATE projects SET retention_days = :days "
                "WHERE id = :id AND org_id = :org RETURNING id"
            ),
            {"days": body.retention_days, "id": project_id, "org": user["org_id"]},
        )
        if not result.one_or_none():
            raise HTTPException(404, "Project not found")

        await db.commit()

    await log_audit(
        org_id=user["org_id"],
        user_id=user["sub"],
        action="project.settings.update",
        resource_id=project_id,
        metadata={"retention_days": body.retention_days},
    )

    return {"retention_days": body.retention_days}
