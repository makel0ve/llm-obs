import hashlib
import uuid

import pytest
from sqlalchemy import text


@pytest.mark.asyncio
async def test_register_returns_default_project_credentials(client, db_session):
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
