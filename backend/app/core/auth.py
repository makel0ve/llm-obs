import hashlib
import json
from datetime import UTC, datetime, timedelta
from typing import Any, Literal, cast

from fastapi import Depends, Header, HTTPException, Query
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from jose import JWTError, jwt
from passlib.context import CryptContext
from sqlalchemy import text

from app.core.config import settings
from app.core.db import get_db
from app.core.redis import get_redis

pwd_context = CryptContext(
    schemes=["bcrypt"], deprecated="auto", bcrypt__rounds=12, truncate_error=False
)
bearer_scheme = HTTPBearer(auto_error=False)
ApiKeyScope = Literal["ingest", "read", "read_write"]
ProjectRole = Literal["viewer", "member"]
PROJECT_ROLE_LEVELS: dict[ProjectRole, int] = {"viewer": 0, "member": 1}


def hash_password(password: str) -> str:
    return pwd_context.hash(password)


def verify_password(plain: str, hashed: str) -> bool:
    return pwd_context.verify(plain, hashed)


def create_access_token(user_id: str, org_id: str, role: str) -> str:
    return jwt.encode(
        {
            "sub": user_id,
            "org_id": org_id,
            "role": role,
            "exp": datetime.now(UTC)
            + timedelta(minutes=settings.jwt_access_token_expire_minutes),
            "iat": datetime.now(UTC),
        },
        settings.secret_key.get_secret_value(),
        algorithm=settings.jwt_algorithm,
    )


def api_key_allows(scope: str | None, required_scope: ApiKeyScope) -> bool:
    if scope == "read_write":
        return True
    return scope == required_scope


def project_role_allows(role: str | None, required_role: ProjectRole) -> bool:
    current_level = PROJECT_ROLE_LEVELS.get(cast(ProjectRole, role), -1)
    required_level = PROJECT_ROLE_LEVELS[required_role]
    return current_level >= required_level


async def load_current_user_from_token(token: str) -> dict[str, Any]:
    try:
        payload = jwt.decode(
            token,
            settings.secret_key.get_secret_value(),
            algorithms=[settings.jwt_algorithm],
        )
        user_id = payload.get("sub")
        if not user_id:
            raise HTTPException(status_code=401)

    except JWTError:
        raise HTTPException(status_code=401, detail="Invalid or expired token")

    async with get_db() as db:
        result = await db.execute(
            text(
                """
                SELECT id, org_id, role, is_platform_admin
                FROM users
                WHERE id = :user_id AND is_active = true
                """
            ),
            {"user_id": user_id},
        )
        user = result.mappings().one_or_none()

    if not user:
        raise HTTPException(status_code=401, detail="Invalid or expired token")

    return {
        "sub": str(user["id"]),
        "org_id": str(user["org_id"]),
        "role": user["role"],
        "is_platform_admin": bool(user["is_platform_admin"]),
    }


async def get_current_user(
    creds: HTTPAuthorizationCredentials | None = Depends(bearer_scheme),
) -> dict[str, Any]:
    if not creds:
        raise HTTPException(status_code=401, detail="Not authenticated")

    return await load_current_user_from_token(creds.credentials)


async def get_project_from_api_key(
    creds: HTTPAuthorizationCredentials | None = Depends(bearer_scheme),
    x_api_key: str | None = Header(default=None, alias="X-API-Key"),
    required_scope: ApiKeyScope = "ingest",
) -> dict[str, Any]:
    api_key = x_api_key or (creds.credentials if creds else None)
    if not api_key:
        raise HTTPException(status_code=401, detail="API key required")

    key_hash = hashlib.sha256(api_key.encode()).hexdigest()
    redis = await get_redis()
    cache_key = f"apikey:{key_hash}"

    cached = await redis.get(cache_key)
    if cached:
        cached_project = cast(dict[str, Any], json.loads(cached))
        if not api_key_allows(cached_project.get("scope"), required_scope):
            raise HTTPException(status_code=403, detail="API key scope denied")
        return cached_project

    async with get_db() as db:
        r = await db.execute(
            text(
                """
                SELECT p.id, p.org_id, p.name, 'read_write' AS scope,
                    NULL AS api_key_id, true AS legacy
                FROM projects p
                WHERE p.api_key_hash = :h AND p.is_active = true
                UNION ALL
                SELECT p.id, p.org_id, p.name, pak.scope,
                    pak.id AS api_key_id, false AS legacy
                FROM project_api_keys pak
                JOIN projects p ON p.id = pak.project_id
                WHERE pak.key_hash = :h
                    AND pak.is_active = true
                    AND pak.revoked_at IS NULL
                    AND p.is_active = true
                LIMIT 1
                """
            ),
            {"h": key_hash},
        )
        project_row = r.mappings().one_or_none()

        if project_row and project_row["api_key_id"]:
            await db.execute(
                text("UPDATE project_api_keys SET last_used_at = :now WHERE id = :id"),
                {"id": project_row["api_key_id"], "now": datetime.now(UTC)},
            )
            await db.commit()

    if not project_row:
        raise HTTPException(status_code=401, detail="Invalid API key")

    pd: dict[str, Any] = dict(project_row)
    if not api_key_allows(pd.get("scope"), required_scope):
        raise HTTPException(status_code=403, detail="API key scope denied")

    await redis.setex(cache_key, 60, json.dumps(pd, default=str))

    return pd


async def get_project_for_user(
    project_id: str,
    user: dict[str, Any],
    required_role: ProjectRole = "viewer",
) -> dict[str, Any]:
    async with get_db() as db:
        r = await db.execute(
            text(
                """
                SELECT p.id, p.org_id, p.name, pm.role AS project_role
                FROM projects p
                LEFT JOIN project_memberships pm
                    ON pm.project_id = p.id AND pm.user_id = :user_id
                WHERE p.id = :pid AND p.org_id = :org AND p.is_active = true
                """
            ),
            {
                "pid": project_id,
                "org": user["org_id"],
                "user_id": user["sub"],
            },
        )
        project = r.mappings().one_or_none()

    if not project:
        raise HTTPException(status_code=404, detail="Project not found")

    result = dict(project)
    if user.get("role") == "admin":
        result["project_role"] = "admin"
        return result

    if not project_role_allows(result.get("project_role"), required_role):
        raise HTTPException(status_code=403, detail="Project access denied")

    return result


async def get_project_from_token_or_api_key(
    creds: HTTPAuthorizationCredentials | None = Depends(bearer_scheme),
    x_api_key: str | None = Header(default=None, alias="X-API-Key"),
    project_id: str | None = Query(default=None),
) -> dict[str, Any]:
    if x_api_key:
        return await get_project_from_api_key(
            creds=None, x_api_key=x_api_key, required_scope="read"
        )

    if creds and project_id:
        user = await load_current_user_from_token(creds.credentials)
        return await get_project_for_user(project_id, user)

    raise HTTPException(status_code=401, detail="Authentication required")
