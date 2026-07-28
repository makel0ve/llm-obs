import hashlib
import uuid
from collections.abc import Generator

import pytest
from fastapi import Response
from sqlalchemy import text

from app.core.auth import create_access_token
from app.core.ratelimit import get_auth_rate_limiter
from app.main import app


class NoopAuthRateLimiter:
    async def check(
        self,
        *,
        identifier: str,
        action: str,
        response: Response,
    ) -> None:
        return None


@pytest.fixture(autouse=True)
def disable_auth_rate_limit_for_project_api_tests() -> Generator[None, None, None]:
    app.dependency_overrides[get_auth_rate_limiter] = lambda: NoopAuthRateLimiter()
    yield
    app.dependency_overrides.pop(get_auth_rate_limiter, None)


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


async def get_project_org_id(db_session, project_id: str) -> str:
    result = await db_session.execute(
        text("SELECT org_id FROM projects WHERE id = :id"),
        {"id": project_id},
    )
    return str(result.mappings().one()["org_id"])


async def create_org_user(db_session, org_id: str, *, role: str = "member") -> str:
    user_id = str(uuid.uuid4())
    await db_session.execute(
        text(
            """
            INSERT INTO users (id, org_id, email, password_hash, role)
            VALUES (:id, :org_id, :email, :password_hash, :role)
            """
        ),
        {
            "id": user_id,
            "org_id": org_id,
            "email": f"{user_id}@example.com",
            "password_hash": "not-used",
            "role": role,
        },
    )
    await db_session.commit()
    return user_id


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
    member_id = await create_org_user(db_session, org_id, role="member")
    member_token = create_access_token(member_id, org_id, "member")
    headers = {"Authorization": f"Bearer {member_token}"}

    listed = await client.get("/v1/projects", headers=headers)
    created = await client.post(
        "/v1/projects",
        json={"name": "Forbidden"},
        headers=headers,
    )

    assert listed.status_code == 403
    assert created.status_code == 403


@pytest.mark.asyncio
async def test_admin_can_assign_update_list_and_remove_project_member(
    client, db_session
):
    registration = await register_org(client, "Project Members Org")
    admin_headers = {"Authorization": f"Bearer {registration['access_token']}"}
    org_id = await get_project_org_id(db_session, registration["project_id"])
    user_id = await create_org_user(db_session, org_id, role="viewer")
    user_headers = {
        "Authorization": f"Bearer {create_access_token(user_id, org_id, 'viewer')}"
    }

    initially_accessible = await client.get(
        "/v1/projects/accessible", headers=user_headers
    )
    assigned = await client.post(
        f"/v1/projects/{registration['project_id']}/members",
        json={"user_id": user_id, "role": "member"},
        headers=admin_headers,
    )
    listed = await client.get(
        f"/v1/projects/{registration['project_id']}/members",
        headers=admin_headers,
    )
    after_assign_accessible = await client.get(
        "/v1/projects/accessible", headers=user_headers
    )
    updated = await client.post(
        f"/v1/projects/{registration['project_id']}/members",
        json={"user_id": user_id, "role": "viewer"},
        headers=admin_headers,
    )
    removed = await client.delete(
        f"/v1/projects/{registration['project_id']}/members/{user_id}",
        headers=admin_headers,
    )
    after_remove_accessible = await client.get(
        "/v1/projects/accessible", headers=user_headers
    )

    assert initially_accessible.status_code == 200
    assert initially_accessible.json() == []
    assert assigned.status_code == 201
    assert assigned.json()["user_id"] == user_id
    assert assigned.json()["project_role"] == "member"
    assert listed.status_code == 200
    assert [member["user_id"] for member in listed.json()] == [user_id]
    assert after_assign_accessible.status_code == 200
    assert after_assign_accessible.json()[0]["id"] == registration["project_id"]
    assert after_assign_accessible.json()[0]["project_role"] == "member"
    assert updated.status_code == 201
    assert updated.json()["project_role"] == "viewer"
    assert removed.status_code == 204
    assert after_remove_accessible.status_code == 200
    assert after_remove_accessible.json() == []


@pytest.mark.asyncio
async def test_accessible_projects_returns_all_org_projects_for_admin(client):
    registration = await register_org(client, "Accessible Admin Org")
    headers = {"Authorization": f"Bearer {registration['access_token']}"}

    created = await client.post(
        "/v1/projects",
        json={"name": "Secondary"},
        headers=headers,
    )
    accessible = await client.get("/v1/projects/accessible", headers=headers)

    assert created.status_code == 201
    assert accessible.status_code == 200
    projects = {project["name"]: project for project in accessible.json()}
    assert {"Default", "Secondary"} <= set(projects)
    assert {project["project_role"] for project in projects.values()} == {"admin"}


@pytest.mark.asyncio
async def test_project_member_management_requires_admin(client, db_session):
    registration = await register_org(client, "Project Members Admin Required Org")
    org_id = await get_project_org_id(db_session, registration["project_id"])
    user_id = await create_org_user(db_session, org_id, role="member")
    member_headers = {
        "Authorization": f"Bearer {create_access_token(user_id, org_id, 'member')}"
    }

    listed = await client.get(
        f"/v1/projects/{registration['project_id']}/members",
        headers=member_headers,
    )
    assigned = await client.post(
        f"/v1/projects/{registration['project_id']}/members",
        json={"user_id": user_id, "role": "viewer"},
        headers=member_headers,
    )
    removed = await client.delete(
        f"/v1/projects/{registration['project_id']}/members/{user_id}",
        headers=member_headers,
    )

    assert listed.status_code == 403
    assert assigned.status_code == 403
    assert removed.status_code == 403


@pytest.mark.asyncio
async def test_project_member_assignment_rejects_user_from_other_org(
    client, db_session
):
    org_a = await register_org(client, "Project Members Org A")
    org_b = await register_org(client, "Project Members Org B")
    headers_a = {"Authorization": f"Bearer {org_a['access_token']}"}
    org_b_id = await get_project_org_id(db_session, org_b["project_id"])
    foreign_user_id = await create_org_user(db_session, org_b_id, role="member")

    assigned = await client.post(
        f"/v1/projects/{org_a['project_id']}/members",
        json={"user_id": foreign_user_id, "role": "viewer"},
        headers=headers_a,
    )

    assert assigned.status_code == 404
