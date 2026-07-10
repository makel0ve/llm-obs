import hashlib
import secrets
import uuid
from datetime import UTC, datetime, timedelta
from typing import Any

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import text

from app.core.auth import create_access_token, get_current_user, hash_password
from app.core.db import get_db
from app.core.rbac import require_admin
from app.schemas.users import UserInviteAccept, UserInviteCreate, UserRoleUpdate
from app.services.audit import log_audit

router = APIRouter(prefix="/v1/users", tags=["users"])
INVITE_TTL_HOURS = 24


def hash_invite_token(token: str) -> str:
    return hashlib.sha256(token.encode()).hexdigest()


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

            invite_id = str(uuid.uuid4())
            raw_token = secrets.token_urlsafe(32)
            token_hash = hash_invite_token(raw_token)
            expires_at = datetime.now(UTC) + timedelta(hours=INVITE_TTL_HOURS)
            result = await db.execute(
                text(
                    """
                    INSERT INTO organization_invites
                    (id, org_id, email, role, token_hash, expires_at,
                     created_by_user_id)
                    VALUES (:id, :org, :email, :role, :token_hash, :expires_at,
                            :created_by)
                    RETURNING id, email, role, expires_at
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
                },
            )

            invite = dict(result.mappings().one())
            invite["invite_token"] = raw_token

    await log_audit(
        org_id=user["org_id"],
        user_id=user["sub"],
        action="user.invite.create",
        resource_id=invite["id"],
        metadata={"email": body.email, "role": body.role},
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
                    SELECT id, org_id, email, role, expires_at
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

    await log_audit(
        org_id=str(invite["org_id"]),
        user_id=user_id,
        action="user.invite.accept",
        resource_id=str(invite["id"]),
        metadata={"email": invite["email"], "role": invite["role"]},
    )

    return {
        "access_token": create_access_token(
            user_id, str(invite["org_id"]), invite["role"]
        ),
        "token_type": "bearer",
        "role": invite["role"],
        "project_id": str(default_project["id"]) if default_project else None,
    }


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
