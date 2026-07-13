import hashlib
import uuid

import pytest
from sqlalchemy import text

from app.core.auth import create_access_token


async def register_org(client, org_name: str) -> dict:
    email = f"{org_name.lower().replace(' ', '-')}-{uuid.uuid4().hex}@example.com"
    response = await client.post(
        "/v1/auth/register",
        json={
            "email": email,
            "password": "correct-horse-battery-staple",
            "org_name": org_name,
        },
    )
    assert response.status_code == 201
    return response.json()


@pytest.mark.asyncio
async def test_admin_can_create_and_list_org_projects(client, db_session):
    registration = await register_org(client, "Project API Org")
    headers = {"Authorization": f"Bearer {registration['access_token']}"}

    created = await client.post(
        "/v1/projects",
        json={"name": "Production", "retention_days": 120},
        headers=headers,
    )

    assert created.status_code == 201
    created_body = created.json()
    assert created_body["id"]
    assert created_body["name"] == "Production"
    assert created_body["retention_days"] == 120
    assert created_body["api_key"].startswith("llmobs_")

    stored = await db_session.execute(
        text("SELECT api_key_hash FROM projects WHERE id = :id"),
        {"id": created_body["id"]},
    )
    row = stored.mappings().one()
    assert (
        row["api_key_hash"]
        == hashlib.sha256(created_body["api_key"].encode()).hexdigest()
    )

    listed = await client.get("/v1/projects", headers=headers)

    assert listed.status_code == 200
    project_names = {project["name"] for project in listed.json()}
    assert {"Default", "Production"} <= project_names


@pytest.mark.asyncio
async def test_project_list_scopes_to_admin_org(client):
    org_a = await register_org(client, "Scoped Projects A")
    org_b = await register_org(client, "Scoped Projects B")
    headers_a = {"Authorization": f"Bearer {org_a['access_token']}"}
    headers_b = {"Authorization": f"Bearer {org_b['access_token']}"}

    created = await client.post(
        "/v1/projects",
        json={"name": "Only A"},
        headers=headers_a,
    )
    assert created.status_code == 201

    listed_a = await client.get("/v1/projects", headers=headers_a)
    listed_b = await client.get("/v1/projects", headers=headers_b)

    assert listed_a.status_code == 200
    assert listed_b.status_code == 200
    assert "Only A" in {project["name"] for project in listed_a.json()}
    assert "Only A" not in {project["name"] for project in listed_b.json()}


@pytest.mark.asyncio
async def test_create_project_rejects_duplicate_org_name(client):
    registration = await register_org(client, "Duplicate Project Org")
    headers = {"Authorization": f"Bearer {registration['access_token']}"}

    first = await client.post(
        "/v1/projects",
        json={"name": "Analytics"},
        headers=headers,
    )
    second = await client.post(
        "/v1/projects",
        json={"name": "Analytics"},
        headers=headers,
    )

    assert first.status_code == 201
    assert second.status_code == 409


@pytest.mark.asyncio
async def test_project_lifecycle_requires_admin(client, db_session):
    registration = await register_org(client, "Member Project Org")
    org = await db_session.execute(
        text("SELECT org_id FROM projects WHERE id = :id"),
        {"id": registration["project_id"]},
    )
    org_id = str(org.mappings().one()["org_id"])
    member_token = create_access_token(str(uuid.uuid4()), org_id, "member")
    headers = {"Authorization": f"Bearer {member_token}"}

    listed = await client.get("/v1/projects", headers=headers)
    created = await client.post(
        "/v1/projects",
        json={"name": "Forbidden"},
        headers=headers,
    )

    assert listed.status_code == 403
    assert created.status_code == 403
