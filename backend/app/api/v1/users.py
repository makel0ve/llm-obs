import hashlib
import json
import secrets
import uuid
from datetime import UTC, datetime, timedelta
from typing import Any

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import text

from app.core.auth import create_access_token, get_current_user, hash_password
from app.core.db import get_db
from app.core.rbac import require_admin
from app.schemas.users import (
    UserInviteAccept,
    UserInviteCreate,
    UserProjectAccessRecord,
    UserRoleUpdate,
)
from app.services.audit import log_audit

router = APIRouter(prefix="/v1/users", tags=["users"])
INVITE_TTL_HOURS = 24


def hash_invite_token(token: str) -> str:
    return hashlib.sha256(token.encode()).hexdigest()


def serialize_project_assignments(value: Any) -> list[dict[str, str]]:
    if not value:
        return []

    if not isinstance(value, list):
        raise HTTPException(400, "Invite project assignments are invalid")

    assignments: list[dict[str, str]] = []
    for item in value:
        if not isinstance(item, dict):
            raise HTTPException(400, "Invite project assignments are invalid")
        project_id = item.get("project_id")
        role = item.get("role")
        if not isinstance(project_id, str) or role not in {"member", "viewer"}:
            raise HTTPException(400, "Invite project assignments are invalid")
        assignments.append({"project_id": project_id, "role": role})
    return assignments


async def validate_invite_project_assignments(
    db: Any, body: UserInviteCreate, org_id: str
) -> list[dict[str, str]]:
    assignments = [
        assignment.model_dump(mode="json") for assignment in body.project_assignments
    ]
    if not assignments:
        return []

    project_ids = [assignment["project_id"] for assignment in assignments]
    result = await db.execute(
        text(
            """
            SELECT id
            FROM projects
            WHERE org_id = :org
                AND is_active = true
                AND id = ANY(CAST(:project_ids AS uuid[]))
            """
        ),
        {"org": org_id, "project_ids": project_ids},
    )
    found = {str(row["id"]) for row in result.mappings().all()}
    if found != set(project_ids):
        raise HTTPException(400, "One or more selected projects are invalid")

    return assignments


@router.get("")
async def list_users(user: dict[str, Any] = Depends(get_current_user)) -> list[Any]:
    require_admin(user)

    async with get_db() as db:
        result = await db.execute(
            text(
                """
                SELECT id, email, role, is_active, created_at
                FROM users
                WHERE org_id = :org
                ORDER BY created_at ASC, email ASC
                """
            ),
            {"org": user["org_id"]},
        )

        return [dict(row) for row in result.mappings().all()]


@router.post("/invites", status_code=201)
async def create_invite(
    body: UserInviteCreate, user: dict[str, Any] = Depends(get_current_user)
) -> dict[str, Any]:
    require_admin(user)

    async with get_db() as db:
        async with db.begin():
            exists = await db.execute(
                text("SELECT 1 FROM users WHERE email = :email"),
                {"email": body.email},
            )
            if exists.one_or_none():
                raise HTTPException(409, "Email already registered")

            project_assignments = await validate_invite_project_assignments(
                db, body, user["org_id"]
            )
            invite_id = str(uuid.uuid4())
            raw_token = secrets.token_urlsafe(32)
            token_hash = hash_invite_token(raw_token)
            expires_at = datetime.now(UTC) + timedelta(hours=INVITE_TTL_HOURS)
            result = await db.execute(
                text(
                    """
                    INSERT INTO organization_invites
                    (id, org_id, email, role, token_hash, expires_at,
                     created_by_user_id, project_assignments)
                    VALUES (:id, :org, :email, :role, :token_hash, :expires_at,
                            :created_by, CAST(:project_assignments AS jsonb))
                    RETURNING id, email, role, project_assignments, expires_at
                    """
                ),
                {
                    "id": invite_id,
                    "org": user["org_id"],
                    "email": body.email,
                    "role": body.role,
                    "token_hash": token_hash,
                    "expires_at": expires_at,
                    "created_by": user["sub"],
                    "project_assignments": json.dumps(project_assignments),
                },
            )

            invite = dict(result.mappings().one())
            invite["project_assignments"] = serialize_project_assignments(
                invite.get("project_assignments")
            )
            invite["invite_token"] = raw_token

    await log_audit(
        org_id=user["org_id"],
        user_id=user["sub"],
        action="user.invite.create",
        resource_id=invite["id"],
        metadata={
            "email": body.email,
            "role": body.role,
            "project_assignment_count": len(invite["project_assignments"]),
        },
    )

    return invite


@router.post("/invites/accept")
async def accept_invite(body: UserInviteAccept) -> dict[str, Any]:
    token_hash = hash_invite_token(body.token)
    now = datetime.now(UTC)

    async with get_db() as db:
        async with db.begin():
            current = await db.execute(
                text(
                    """
                    SELECT id, org_id, email, role, project_assignments, expires_at
                    FROM organization_invites
                    WHERE token_hash = :token_hash AND accepted_at IS NULL
                    FOR UPDATE
                    """
                ),
                {"token_hash": token_hash},
            )
            invite = current.mappings().one_or_none()
            if not invite:
                raise HTTPException(400, "Invite is invalid or already accepted")

            if invite["expires_at"] <= now:
                raise HTTPException(400, "Invite has expired")

            exists = await db.execute(
                text("SELECT 1 FROM users WHERE email = :email"),
                {"email": invite["email"]},
            )
            if exists.one_or_none():
                raise HTTPException(409, "Email already registered")

            user_id = str(uuid.uuid4())
            await db.execute(
                text(
                    """
                    INSERT INTO users (id, org_id, email, password_hash, role)
                    VALUES (:id, :org, :email, :password_hash, :role)
                    """
                ),
                {
                    "id": user_id,
                    "org": str(invite["org_id"]),
                    "email": invite["email"],
                    "password_hash": hash_password(body.password),
                    "role": invite["role"],
                },
            )
            project_assignments = serialize_project_assignments(
                invite["project_assignments"]
            )
            for assignment in project_assignments:
                await db.execute(
                    text(
                        """
                        INSERT INTO project_memberships (
                            id, project_id, user_id, role
                        )
                        VALUES (:id, :project_id, :user_id, :role)
                        ON CONFLICT (project_id, user_id)
                        DO UPDATE SET
                            role = EXCLUDED.role,
                            updated_at = TIMEZONE('utc', now())
                        """
                    ),
                    {
                        "id": str(uuid.uuid4()),
                        "project_id": assignment["project_id"],
                        "user_id": user_id,
                        "role": assignment["role"],
                    },
                )
            await db.execute(
                text(
                    """
                    UPDATE organization_invites
                    SET accepted_at = :now
                    WHERE id = :id
                    """
                ),
                {"id": invite["id"], "now": now},
            )
            project = await db.execute(
                text(
                    "SELECT id FROM projects WHERE org_id = :org AND is_active = true "
                    "LIMIT 1"
                ),
                {"org": str(invite["org_id"])},
            )
            default_project = project.mappings().one_or_none()
            selected_project_id = (
                project_assignments[0]["project_id"]
                if project_assignments
                else str(default_project["id"])
                if default_project
                else None
            )

    await log_audit(
        org_id=str(invite["org_id"]),
        user_id=user_id,
        action="user.invite.accept",
        resource_id=str(invite["id"]),
        metadata={
            "email": invite["email"],
            "role": invite["role"],
            "project_assignment_count": len(
                serialize_project_assignments(invite["project_assignments"])
            ),
        },
    )

    return {
        "access_token": create_access_token(
            user_id, str(invite["org_id"]), invite["role"]
        ),
        "token_type": "bearer",
        "role": invite["role"],
        "project_id": selected_project_id,
    }


@router.get("/{user_id}/projects", response_model=list[UserProjectAccessRecord])
async def list_user_project_access(
    user_id: str,
    user: dict[str, Any] = Depends(get_current_user),
) -> list[Any]:
    require_admin(user)

    async with get_db() as db:
        target = await db.execute(
            text(
                """
                SELECT id, role
                FROM users
                WHERE id = :id AND org_id = :org AND is_active = true
                """
            ),
            {"id": user_id, "org": user["org_id"]},
        )
        target_user = target.mappings().one_or_none()
        if not target_user:
            raise HTTPException(404, "User not found")

        result = await db.execute(
            text(
                """
                SELECT p.id AS project_id, p.name AS project_name,
                    p.is_active, p.retention_days,
                    CASE
                        WHEN :target_role = 'admin' THEN 'admin'
                        ELSE pm.role
                    END AS project_role
                FROM projects p
                LEFT JOIN project_memberships pm
                    ON pm.project_id = p.id
                    AND pm.user_id = :user_id
                WHERE p.org_id = :org
                    AND p.is_active = true
                ORDER BY p.created_at ASC, p.name ASC
                """
            ),
            {
                "user_id": user_id,
                "org": user["org_id"],
                "target_role": target_user["role"],
            },
        )

    return [
        {
            **dict(row),
            "project_id": str(row["project_id"]),
        }
        for row in result.mappings().all()
    ]


@router.patch("/{user_id}/role")
async def update_user_role(
    user_id: str,
    body: UserRoleUpdate,
    user: dict[str, Any] = Depends(get_current_user),
) -> Any:
    require_admin(user)

    if user_id == user["sub"] and body.role != "admin":
        raise HTTPException(400, "Cannot remove your own admin role")

    async with get_db() as db:
        async with db.begin():
            current = await db.execute(
                text(
                    """
                    SELECT id, email, role
                    FROM users
                    WHERE id = :id AND org_id = :org AND is_active = true
                    FOR UPDATE
                    """
                ),
                {"id": user_id, "org": user["org_id"]},
            )
            target = current.mappings().one_or_none()
            if not target:
                raise HTTPException(404, "User not found")

            if target["role"] == "admin" and body.role != "admin":
                admins = await db.execute(
                    text(
                        """
                        SELECT count(*) AS count
                        FROM users
                        WHERE org_id = :org AND role = 'admin' AND is_active = true
                        """
                    ),
                    {"org": user["org_id"]},
                )
                if admins.mappings().one()["count"] <= 1:
                    raise HTTPException(
                        400, "Organization must keep at least one admin"
                    )

            result = await db.execute(
                text(
                    """
                    UPDATE users
                    SET role = :role
                    WHERE id = :id AND org_id = :org
                    RETURNING id, email, role, is_active, created_at
                    """
                ),
                {"id": user_id, "org": user["org_id"], "role": body.role},
            )

            updated = result.mappings().one()

    await log_audit(
        org_id=user["org_id"],
        user_id=user["sub"],
        action="user.role.update",
        resource_id=user_id,
        metadata={
            "email": target["email"],
            "old_role": target["role"],
            "new_role": body.role,
        },
    )

    return updated


@router.delete("/{user_id}", status_code=204)
async def delete_user(
    user_id: str, user: dict[str, Any] = Depends(get_current_user)
) -> None:
    require_admin(user)

    if user_id == user["sub"]:
        raise HTTPException(400, "Cannot delete your own user")

    async with get_db() as db:
        async with db.begin():
            current = await db.execute(
                text(
                    """
                    SELECT id, email, role
                    FROM users
                    WHERE id = :id AND org_id = :org AND is_active = true
                    FOR UPDATE
                    """
                ),
                {"id": user_id, "org": user["org_id"]},
            )
            target = current.mappings().one_or_none()
            if not target:
                raise HTTPException(404, "User not found")

            if target["role"] == "admin":
                admins = await db.execute(
                    text(
                        """
                        SELECT count(*) AS count
                        FROM users
                        WHERE org_id = :org AND role = 'admin' AND is_active = true
                        """
                    ),
                    {"org": user["org_id"]},
                )
                if admins.mappings().one()["count"] <= 1:
                    raise HTTPException(
                        400, "Organization must keep at least one admin"
                    )

            result = await db.execute(
                text(
                    """
                    DELETE FROM users
                    WHERE id = :id AND org_id = :org
                    RETURNING id
                    """
                ),
                {"id": user_id, "org": user["org_id"]},
            )
            if not result.one_or_none():
                raise HTTPException(404, "User not found")

    await log_audit(
        org_id=user["org_id"],
        user_id=user["sub"],
        action="user.delete",
        resource_id=user_id,
        metadata={"email": target["email"], "role": target["role"]},
    )
