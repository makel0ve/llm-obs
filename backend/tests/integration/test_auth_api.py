import hashlib
import uuid

import pytest
from httpx import AsyncClient
from pydantic import SecretStr
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession, create_async_engine

from app.core.config import settings


async def clear_bootstrap_state() -> None:
    engine = create_async_engine(
        settings.effective_migration_database_url.get_secret_value(),
        connect_args={"timeout": 5},
    )
    try:
        async with engine.begin() as connection:
            await connection.execute(text("TRUNCATE organizations CASCADE"))
    finally:
        await engine.dispose()


@pytest.mark.asyncio
async def test_register_returns_default_project_credentials(
    client: AsyncClient,
    db_session: AsyncSession,
) -> None:
    email = f"registration-{uuid.uuid4().hex}@example.com"

    r = await client.post(
        "/v1/auth/register",
        json={
            "email": email,
            "password": "correct-horse-battery-staple",
            "org_name": "Registration Contract Test",
        },
    )

    assert r.status_code == 201
    body = r.json()

    assert body["access_token"]
    assert body["token_type"] == "bearer"
    assert body["api_key"].startswith("llmobs_")
    assert body["project_id"]

    project = await db_session.execute(
        text(
            """
            SELECT p.id, p.name, p.api_key_hash, u.email
            FROM projects p
            JOIN users u ON u.org_id = p.org_id
            WHERE p.id = :project_id
            """
        ),
        {"project_id": body["project_id"]},
    )
    row = project.mappings().one()

    assert str(row["id"]) == body["project_id"]
    assert row["name"] == "Default"
    assert row["email"] == email
    assert row["api_key_hash"] == hashlib.sha256(body["api_key"].encode()).hexdigest()


@pytest.mark.asyncio
async def test_register_bootstraps_first_admin_when_public_registration_disabled(
    client: AsyncClient,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    await clear_bootstrap_state()
    monkeypatch.setattr(settings, "public_registration_enabled", False)
    monkeypatch.setattr(
        settings,
        "bootstrap_admin_token",
        SecretStr("test-bootstrap-token"),
    )

    rejected = await client.post(
        "/v1/auth/register",
        json={
            "email": "bootstrap-rejected@example.com",
            "password": "correct-horse-battery-staple",
            "org_name": "Bootstrap Rejected",
            "bootstrap_token": "wrong-token",
        },
    )
    accepted = await client.post(
        "/v1/auth/register",
        json={
            "email": "bootstrap-admin@example.com",
            "password": "correct-horse-battery-staple",
            "org_name": "Bootstrap Org",
            "bootstrap_token": "test-bootstrap-token",
        },
    )
    closed = await client.post(
        "/v1/auth/register",
        json={
            "email": "bootstrap-second@example.com",
            "password": "correct-horse-battery-staple",
            "org_name": "Bootstrap Second",
            "bootstrap_token": "test-bootstrap-token",
        },
    )

    assert rejected.status_code == 403
    assert rejected.json()["detail"] == "Invalid bootstrap token"
    assert accepted.status_code == 201
    assert accepted.json()["role"] == "admin"
    assert accepted.json()["api_key"].startswith("llmobs_")
    assert closed.status_code == 403
    assert closed.json()["detail"] == "Registration is disabled"


@pytest.mark.asyncio
async def test_register_rejects_duplicate_email(
    client: AsyncClient,
    db_session: AsyncSession,
) -> None:
    email = f"duplicate-{uuid.uuid4().hex}@example.com"
    payload = {
        "email": email,
        "password": "correct-horse-battery-staple",
        "org_name": "Duplicate Registration Test",
    }

    first = await client.post("/v1/auth/register", json=payload)
    second = await client.post("/v1/auth/register", json=payload)

    assert first.status_code == 201
    assert second.status_code == 409

    counts = await db_session.execute(
        text(
            """
            SELECT
                COUNT(DISTINCT u.id) AS users,
                COUNT(DISTINCT p.id) AS projects
            FROM users u
            LEFT JOIN projects p ON p.org_id = u.org_id
            WHERE u.email = :email
            """
        ),
        {"email": email},
    )
    row = counts.mappings().one()

    assert row["users"] == 1
    assert row["projects"] == 1
