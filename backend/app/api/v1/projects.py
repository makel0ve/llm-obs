import hashlib
import secrets
import uuid
from typing import Any

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import text

from app.core.auth import get_current_user
from app.core.db import get_db
from app.core.rbac import require_admin
from app.core.redis import get_redis
from app.schemas.projects import (
    ProjectApiKeyCreate,
    ProjectApiKeyCreateResponse,
    ProjectApiKeyRecord,
    ProjectSettingsUpdate,
)
from app.services.audit import log_audit

router = APIRouter(prefix="/v1/projects", tags=["projects"])


def serialize_api_key_record(row: Any) -> dict[str, Any]:
    record = dict(row)
    record["id"] = str(record["id"])
    return record


@router.post("/{project_id}/rotate-key")
async def rotate_api_key(
    project_id: str, user: dict[str, Any] = Depends(get_current_user)
) -> dict[str, str]:
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


@router.get("/{project_id}/api-keys", response_model=list[ProjectApiKeyRecord])
async def list_api_keys(
    project_id: str, user: dict[str, Any] = Depends(get_current_user)
) -> list[Any]:
    require_admin(user)

    async with get_db() as db:
        project = await db.execute(
            text("SELECT id FROM projects WHERE id = :id AND org_id = :org"),
            {"id": project_id, "org": user["org_id"]},
        )
        if not project.one_or_none():
            raise HTTPException(404, "Project not found")

        result = await db.execute(
            text(
                """
                SELECT id, name, description, scope, is_active, created_at,
                    last_used_at, revoked_at
                FROM project_api_keys
                WHERE project_id = :project_id
                ORDER BY created_at DESC
                """
            ),
            {"project_id": project_id},
        )

        return [serialize_api_key_record(row) for row in result.mappings().all()]


@router.post(
    "/{project_id}/api-keys",
    status_code=201,
    response_model=ProjectApiKeyCreateResponse,
)
async def create_api_key(
    project_id: str,
    body: ProjectApiKeyCreate,
    user: dict[str, Any] = Depends(get_current_user),
) -> dict[str, Any]:
    require_admin(user)

    raw_key = f"llmobs_{secrets.token_urlsafe(32)}"
    key_hash = hashlib.sha256(raw_key.encode()).hexdigest()

    async with get_db() as db:
        async with db.begin():
            project = await db.execute(
                text("SELECT id FROM projects WHERE id = :id AND org_id = :org"),
                {"id": project_id, "org": user["org_id"]},
            )
            if not project.one_or_none():
                raise HTTPException(404, "Project not found")

            result = await db.execute(
                text(
                    """
                    INSERT INTO project_api_keys
                    (id, project_id, name, description, key_hash, scope)
                    VALUES (:id, :project_id, :name, :description,
                            :key_hash, :scope)
                    RETURNING id, name, description, scope, is_active, created_at,
                        last_used_at, revoked_at
                    """
                ),
                {
                    "id": str(uuid.uuid4()),
                    "project_id": project_id,
                    "name": body.name.strip(),
                    "description": body.description.strip()
                    if body.description
                    else None,
                    "key_hash": key_hash,
                    "scope": body.scope,
                },
            )

            record = serialize_api_key_record(result.mappings().one())
            record["api_key"] = raw_key

    await log_audit(
        org_id=user["org_id"],
        user_id=user["sub"],
        action="api_key.create",
        resource_id=project_id,
        metadata={"name": body.name, "scope": body.scope},
    )

    return record


@router.post("/{project_id}/api-keys/{key_id}/revoke")
async def revoke_api_key(
    project_id: str,
    key_id: str,
    user: dict[str, Any] = Depends(get_current_user),
) -> dict[str, bool]:
    require_admin(user)

    async with get_db() as db:
        async with db.begin():
            result = await db.execute(
                text(
                    """
                    UPDATE project_api_keys
                    SET is_active = false,
                        revoked_at = COALESCE(revoked_at, TIMEZONE('utc', now()))
                    WHERE id = :key_id
                        AND project_id IN (
                            SELECT id FROM projects
                            WHERE id = :project_id AND org_id = :org
                        )
                    RETURNING key_hash
                    """
                ),
                {"key_id": key_id, "project_id": project_id, "org": user["org_id"]},
            )
            row = result.mappings().one_or_none()
            if not row:
                raise HTTPException(404, "API key not found")

    redis = await get_redis()
    await redis.delete(f"apikey:{row['key_hash']}")

    await log_audit(
        org_id=user["org_id"],
        user_id=user["sub"],
        action="api_key.revoke",
        resource_id=project_id,
        metadata={"key_id": key_id},
    )

    return {"revoked": True}


@router.patch("/{project_id}/settings")
async def update_settings(
    project_id: str,
    body: ProjectSettingsUpdate,
    user: dict[str, Any] = Depends(get_current_user),
) -> dict[str, int]:
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
