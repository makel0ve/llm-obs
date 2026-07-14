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
    AccessibleProjectRecord,
    ProjectApiKeyCreate,
    ProjectApiKeyCreateResponse,
    ProjectApiKeyRecord,
    ProjectCreate,
    ProjectCreateResponse,
    ProjectMemberAssign,
    ProjectMemberRecord,
    ProjectRecord,
    ProjectSettings,
    ProjectSettingsUpdate,
)
from app.services.audit import log_audit

router = APIRouter(prefix="/v1/projects", tags=["projects"])


def serialize_api_key_record(row: Any) -> dict[str, Any]:
    record = dict(row)
    record["id"] = str(record["id"])
    return record


def serialize_project_record(row: Any) -> dict[str, Any]:
    record = dict(row)
    record["id"] = str(record["id"])
    return record


def serialize_project_member_record(row: Any) -> dict[str, Any]:
    record = dict(row)
    record["user_id"] = str(record["user_id"])
    return record


async def ensure_project_in_org(db: Any, project_id: str, org_id: str) -> None:
    project = await db.execute(
        text(
            """
            SELECT id
            FROM projects
            WHERE id = :id AND org_id = :org AND is_active = true
            """
        ),
        {"id": project_id, "org": org_id},
    )
    if not project.one_or_none():
        raise HTTPException(404, "Project not found")


@router.get("", response_model=list[ProjectRecord])
async def list_projects(
    user: dict[str, Any] = Depends(get_current_user),
) -> list[dict[str, Any]]:
    require_admin(user)

    async with get_db() as db:
        result = await db.execute(
            text(
                """
                SELECT id, name, is_active, created_at, retention_days,
                    payload_storage_mode, payload_max_bytes, payload_redact_keys
                FROM projects
                WHERE org_id = :org
                ORDER BY created_at ASC, name ASC
                """
            ),
            {"org": user["org_id"]},
        )

    return [serialize_project_record(row) for row in result.mappings().all()]


@router.get("/accessible", response_model=list[AccessibleProjectRecord])
async def list_accessible_projects(
    user: dict[str, Any] = Depends(get_current_user),
) -> list[dict[str, Any]]:
    async with get_db() as db:
        if user.get("role") == "admin":
            result = await db.execute(
                text(
                    """
                    SELECT id, name, is_active, created_at, retention_days,
                        payload_storage_mode, payload_max_bytes,
                        payload_redact_keys, 'admin' AS project_role
                    FROM projects
                    WHERE org_id = :org AND is_active = true
                    ORDER BY created_at ASC, name ASC
                    """
                ),
                {"org": user["org_id"]},
            )
        else:
            result = await db.execute(
                text(
                    """
                    SELECT p.id, p.name, p.is_active, p.created_at,
                        p.retention_days, p.payload_storage_mode,
                        p.payload_max_bytes, p.payload_redact_keys,
                        pm.role AS project_role
                    FROM project_memberships pm
                    JOIN projects p ON p.id = pm.project_id
                    WHERE pm.user_id = :user_id
                        AND p.org_id = :org
                        AND p.is_active = true
                    ORDER BY p.created_at ASC, p.name ASC
                    """
                ),
                {"user_id": user["sub"], "org": user["org_id"]},
            )

    return [serialize_project_record(row) for row in result.mappings().all()]


@router.post("", status_code=201, response_model=ProjectCreateResponse)
async def create_project(
    body: ProjectCreate,
    user: dict[str, Any] = Depends(get_current_user),
) -> dict[str, Any]:
    require_admin(user)

    name = body.name.strip()
    if not name:
        raise HTTPException(400, "Project name is required")

    raw_key = f"llmobs_{secrets.token_urlsafe(32)}"
    key_hash = hashlib.sha256(raw_key.encode()).hexdigest()

    async with get_db() as db:
        async with db.begin():
            exists = await db.execute(
                text(
                    """
                    SELECT 1
                    FROM projects
                    WHERE org_id = :org AND name = :name
                    """
                ),
                {"org": user["org_id"], "name": name},
            )
            if exists.one_or_none():
                raise HTTPException(409, "Project already exists")

            result = await db.execute(
                text(
                    """
                    INSERT INTO projects (
                        id, org_id, name, api_key_hash, retention_days,
                        payload_storage_mode, payload_max_bytes, payload_redact_keys
                    )
                    VALUES (
                        :id, :org, :name, :api_key_hash, :retention_days,
                        :payload_storage_mode, :payload_max_bytes,
                        :payload_redact_keys
                    )
                    RETURNING id, name, is_active, created_at, retention_days,
                        payload_storage_mode, payload_max_bytes, payload_redact_keys
                    """
                ),
                {
                    "id": str(uuid.uuid4()),
                    "org": user["org_id"],
                    "name": name,
                    "api_key_hash": key_hash,
                    "retention_days": body.retention_days,
                    "payload_storage_mode": body.payload_storage_mode,
                    "payload_max_bytes": body.payload_max_bytes,
                    "payload_redact_keys": body.payload_redact_keys.strip(),
                },
            )
            record = serialize_project_record(result.mappings().one())

    await log_audit(
        org_id=user["org_id"],
        user_id=user["sub"],
        action="project.create",
        resource_id=record["id"],
        metadata={"name": name},
    )

    record["api_key"] = raw_key
    record["note"] = "Save this key — it won't be shown again"
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


@router.get("/{project_id}/members", response_model=list[ProjectMemberRecord])
async def list_project_members(
    project_id: str,
    user: dict[str, Any] = Depends(get_current_user),
) -> list[dict[str, Any]]:
    require_admin(user)

    async with get_db() as db:
        await ensure_project_in_org(db, project_id, user["org_id"])
        result = await db.execute(
            text(
                """
                SELECT u.id AS user_id, u.email, u.role AS org_role,
                    u.is_active, pm.role AS project_role,
                    pm.created_at, pm.updated_at
                FROM project_memberships pm
                JOIN users u ON u.id = pm.user_id
                WHERE pm.project_id = :project_id
                    AND u.org_id = :org
                ORDER BY u.email ASC
                """
            ),
            {"project_id": project_id, "org": user["org_id"]},
        )

    return [serialize_project_member_record(row) for row in result.mappings().all()]


@router.post(
    "/{project_id}/members",
    status_code=201,
    response_model=ProjectMemberRecord,
)
async def assign_project_member(
    project_id: str,
    body: ProjectMemberAssign,
    user: dict[str, Any] = Depends(get_current_user),
) -> dict[str, Any]:
    require_admin(user)

    async with get_db() as db:
        async with db.begin():
            await ensure_project_in_org(db, project_id, user["org_id"])
            target = await db.execute(
                text(
                    """
                    SELECT id, email, role, is_active
                    FROM users
                    WHERE id = :user_id AND org_id = :org AND is_active = true
                    """
                ),
                {"user_id": body.user_id, "org": user["org_id"]},
            )
            target_user = target.mappings().one_or_none()
            if not target_user:
                raise HTTPException(404, "User not found")

            result = await db.execute(
                text(
                    """
                    INSERT INTO project_memberships (id, project_id, user_id, role)
                    VALUES (:id, :project_id, :user_id, :role)
                    ON CONFLICT (project_id, user_id)
                    DO UPDATE SET
                        role = EXCLUDED.role,
                        updated_at = TIMEZONE('utc', now())
                    RETURNING user_id, role AS project_role, created_at, updated_at
                    """
                ),
                {
                    "id": str(uuid.uuid4()),
                    "project_id": project_id,
                    "user_id": body.user_id,
                    "role": body.role,
                },
            )
            membership = dict(result.mappings().one())

    await log_audit(
        org_id=user["org_id"],
        user_id=user["sub"],
        action="project.member.assign",
        resource_id=project_id,
        metadata={"target_user_id": body.user_id, "role": body.role},
    )

    return serialize_project_member_record(
        {
            **membership,
            "email": target_user["email"],
            "org_role": target_user["role"],
            "is_active": target_user["is_active"],
        }
    )


@router.delete("/{project_id}/members/{user_id}", status_code=204)
async def remove_project_member(
    project_id: str,
    user_id: str,
    user: dict[str, Any] = Depends(get_current_user),
) -> None:
    require_admin(user)

    async with get_db() as db:
        async with db.begin():
            await ensure_project_in_org(db, project_id, user["org_id"])
            target = await db.execute(
                text(
                    """
                    SELECT id
                    FROM users
                    WHERE id = :user_id AND org_id = :org AND is_active = true
                    """
                ),
                {"user_id": user_id, "org": user["org_id"]},
            )
            if not target.one_or_none():
                raise HTTPException(404, "User not found")

            result = await db.execute(
                text(
                    """
                    DELETE FROM project_memberships
                    WHERE project_id = :project_id AND user_id = :user_id
                    RETURNING id
                    """
                ),
                {"project_id": project_id, "user_id": user_id},
            )
            if not result.one_or_none():
                raise HTTPException(404, "Project membership not found")

    await log_audit(
        org_id=user["org_id"],
        user_id=user["sub"],
        action="project.member.remove",
        resource_id=project_id,
        metadata={"target_user_id": user_id},
    )


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


@router.get("/{project_id}/settings", response_model=ProjectSettings)
async def get_settings(
    project_id: str, user: dict[str, Any] = Depends(get_current_user)
) -> dict[str, Any]:
    require_admin(user)

    async with get_db() as db:
        result = await db.execute(
            text(
                """
                SELECT retention_days, payload_storage_mode, payload_max_bytes,
                    payload_redact_keys
                FROM projects
                WHERE id = :id AND org_id = :org
                """
            ),
            {"id": project_id, "org": user["org_id"]},
        )
        row = result.mappings().one_or_none()
        if not row:
            raise HTTPException(404, "Project not found")

    return dict(row)


@router.patch("/{project_id}/settings")
async def update_settings(
    project_id: str,
    body: ProjectSettingsUpdate,
    user: dict[str, Any] = Depends(get_current_user),
) -> dict[str, Any]:
    require_admin(user)
    values = body.model_dump(exclude_unset=True)
    if not values:
        raise HTTPException(400, "No settings provided")

    redact_keys = values.get("payload_redact_keys")
    if isinstance(redact_keys, str):
        values["payload_redact_keys"] = redact_keys.strip()

    async with get_db() as db:
        result = await db.execute(
            text(
                """
                UPDATE projects
                SET retention_days = CASE
                        WHEN :update_retention_days THEN :retention_days
                        ELSE retention_days
                    END,
                    payload_storage_mode = CASE
                        WHEN :update_payload_storage_mode
                        THEN :payload_storage_mode
                        ELSE payload_storage_mode
                    END,
                    payload_max_bytes = CASE
                        WHEN :update_payload_max_bytes THEN :payload_max_bytes
                        ELSE payload_max_bytes
                    END,
                    payload_redact_keys = CASE
                        WHEN :update_payload_redact_keys THEN :payload_redact_keys
                        ELSE payload_redact_keys
                    END
                WHERE id = :id AND org_id = :org
                RETURNING retention_days, payload_storage_mode, payload_max_bytes,
                    payload_redact_keys
                """
            ),
            {
                "id": project_id,
                "org": user["org_id"],
                "update_retention_days": "retention_days" in values,
                "retention_days": values.get("retention_days"),
                "update_payload_storage_mode": "payload_storage_mode" in values,
                "payload_storage_mode": values.get("payload_storage_mode"),
                "update_payload_max_bytes": "payload_max_bytes" in values,
                "payload_max_bytes": values.get("payload_max_bytes"),
                "update_payload_redact_keys": "payload_redact_keys" in values,
                "payload_redact_keys": values.get("payload_redact_keys"),
            },
        )
        row = result.mappings().one_or_none()
        if not row:
            raise HTTPException(404, "Project not found")

        await db.commit()

    await log_audit(
        org_id=user["org_id"],
        user_id=user["sub"],
        action="project.settings.update",
        resource_id=project_id,
        metadata=values,
    )

    return dict(row)
