import hashlib
import json
from datetime import UTC, datetime, timedelta

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


async def get_current_user(
    creds: HTTPAuthorizationCredentials | None = Depends(bearer_scheme),
) -> dict:
    if not creds:
        raise HTTPException(status_code=401, detail="Not authenticated")

    try:
        payload = jwt.decode(
            creds.credentials,
            settings.secret_key.get_secret_value(),
            algorithms=[settings.jwt_algorithm],
        )
        if not payload.get("sub"):
            raise HTTPException(status_code=401)

        return payload

    except JWTError:
        raise HTTPException(status_code=401, detail="Invalid or expired token")


async def get_project_from_api_key(
    creds: HTTPAuthorizationCredentials | None = Depends(bearer_scheme),
    x_api_key: str | None = Header(default=None, alias="X-API-Key"),
) -> dict:
    api_key = x_api_key or (creds.credentials if creds else None)
    if not api_key:
        raise HTTPException(status_code=401, detail="API key required")

    key_hash = hashlib.sha256(api_key.encode()).hexdigest()
    redis = await get_redis()
    cache_key = f"apikey:{key_hash}"

    cached = await redis.get(cache_key)
    if cached:
        return json.loads(cached)

    async with get_db() as db:
        r = await db.execute(
            text(
                "SELECT id, org_id, name FROM projects "
                "WHERE api_key_hash = :h AND is_active = true"
            ),
            {"h": key_hash},
        )
        project = r.mappings().one_or_none()

    if not project:
        raise HTTPException(status_code=401, detail="Invalid API key")

    pd = dict(project)
    await redis.setex(cache_key, 300, json.dumps(pd, default=str))

    return pd


async def get_project_from_token_or_api_key(
    creds: HTTPAuthorizationCredentials | None = Depends(bearer_scheme),
    x_api_key: str | None = Header(default=None, alias="X-API-Key"),
    project_id: str | None = Query(default=None),
) -> dict:
    if x_api_key:
        return await get_project_from_api_key(creds=None, x_api_key=x_api_key)

    if creds and project_id:
        try:
            payload = jwt.decode(
                creds.credentials,
                settings.secret_key.get_secret_value(),
                algorithms=[settings.jwt_algorithm],
            )
            org_id = payload.get("org_id")
            if not org_id:
                raise HTTPException(status_code=401)

            async with get_db() as db:
                r = await db.execute(
                    text(
                        "SELECT id, org_id, name FROM projects "
                        "WHERE id = :pid AND org_id = :org AND is_active = true"
                    ),
                    {"pid": project_id, "org": org_id},
                )
                project = r.mappings().one_or_none()

            if not project:
                raise HTTPException(status_code=404, detail="Project not found")

            return dict(project)

        except JWTError:
            raise HTTPException(status_code=401, detail="Invalid token")

    raise HTTPException(status_code=401, detail="Authentication required")
