import hashlib
import re
import secrets
import uuid

from fastapi import APIRouter, Depends, HTTPException, Request, Response
from sqlalchemy import text

from app.core.auth import create_access_token, hash_password, verify_password
from app.core.db import get_db
from app.core.ratelimit import AuthRateLimiter, get_auth_rate_limiter
from app.schemas.auth import (
    LoginRequest,
    LoginResponse,
    RegisterRequest,
    RegisterResponse,
)

router = APIRouter(prefix="/v1/auth", tags=["auth"])


def auth_rate_limit_identifier(request: Request, action: str) -> str:
    host = request.client.host if request.client else "unknown"
    return f"{action}:{host}"


@router.post("/register", status_code=201, response_model=RegisterResponse)
async def register(
    body: RegisterRequest,
    request: Request,
    response: Response,
    rate_limiter: AuthRateLimiter = Depends(get_auth_rate_limiter),
):
    await rate_limiter.check(
        identifier=auth_rate_limit_identifier(request, "register"),
        action="register",
        response=response,
    )

    async with get_db() as db:
        async with db.begin():
            exists = await db.execute(
                text("SELECT 1 FROM users WHERE email = :e"), {"e": body.email}
            )
            if exists.one_or_none():
                raise HTTPException(409, "Email already registered")

            org_id = str(uuid.uuid4())
            slug = re.sub(r"[^a-z0-9]", "-", body.org_name.lower())[:40]
            slug = f"{slug}-{uuid.uuid4().hex[:6]}"

            await db.execute(
                text(
                    "INSERT INTO organizations (id, name, slug) "
                    "VALUES (:id, :name, :slug)"
                ),
                {"id": org_id, "name": body.org_name, "slug": slug},
            )

            user_id = str(uuid.uuid4())
            await db.execute(
                text(
                    """
                INSERT INTO users (id, org_id, email, password_hash, role)
                VALUES (:id, :org, :email, :hash, 'admin')
                """
                ),
                {
                    "id": user_id,
                    "org": org_id,
                    "email": body.email,
                    "hash": hash_password(body.password),
                },
            )

            project_id = str(uuid.uuid4())
            raw_key = f"llmobs_{secrets.token_urlsafe(32)}"
            key_hash = hashlib.sha256(raw_key.encode()).hexdigest()
            await db.execute(
                text(
                    """
                INSERT INTO projects (id, org_id, name, api_key_hash, retention_days)
                VALUES (:id, :org, 'Default', :hash, :retention)
                """
                ),
                {
                    "id": project_id,
                    "org": org_id,
                    "hash": key_hash,
                    "retention": 90,
                },
            )

    return {
        "access_token": create_access_token(user_id, org_id, "admin"),
        "token_type": "bearer",
        "role": "admin",
        "api_key": raw_key,
        "project_id": project_id,
    }


@router.post("/login", response_model=LoginResponse)
async def login(
    body: LoginRequest,
    request: Request,
    response: Response,
    rate_limiter: AuthRateLimiter = Depends(get_auth_rate_limiter),
):
    await rate_limiter.check(
        identifier=auth_rate_limit_identifier(request, "login"),
        action="login",
        response=response,
    )

    async with get_db() as db:
        r = await db.execute(
            text(
                "SELECT id, org_id, password_hash, role FROM users "
                "WHERE email = :e AND is_active = true"
            ),
            {"e": body.email},
        )
        user = r.mappings().one_or_none()

        dummy = "$2b$12$dummyhashtopreventtimingattacks000000000000000000000000"
        is_valid = verify_password(
            body.password, user["password_hash"] if user else dummy
        )

        if not user or not is_valid:
            raise HTTPException(401, "Invalid credentials")

        p = await db.execute(
            text(
                "SELECT id FROM projects WHERE org_id = :org AND is_active = true "
                "LIMIT 1"
            ),
            {"org": str(user["org_id"])},
        )
        project = p.mappings().one_or_none()

    return {
        "access_token": create_access_token(
            str(user["id"]), str(user["org_id"]), user["role"]
        ),
        "token_type": "bearer",
        "role": user["role"],
        "project_id": str(project["id"]) if project else None,
    }
