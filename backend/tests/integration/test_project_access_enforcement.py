import hashlib
import uuid
from dataclasses import dataclass
from typing import Any

import pytest
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.auth import create_access_token


@dataclass(frozen=True)
class AccessFixture:
    org_id: str
    project_id: str
    user_id: str
    token: str
    api_key: str


async def create_access_fixture(
    db_session: AsyncSession,
    *,
    org_role: str = "member",
    project_role: str | None = None,
) -> AccessFixture:
    org_id = str(uuid.uuid4())
    project_id = str(uuid.uuid4())
    user_id = str(uuid.uuid4())
    api_key = f"llmobs_test_{uuid.uuid4().hex}"
    api_key_hash = hashlib.sha256(api_key.encode()).hexdigest()

    await db_session.execute(
        text("INSERT INTO organizations (id, name, slug) VALUES (:id, :name, :slug)"),
        {"id": org_id, "name": "Access Test Org", "slug": f"access-{org_id[:8]}"},
    )
    await db_session.execute(
        text(
            """
            INSERT INTO projects (id, org_id, name, api_key_hash, retention_days)
            VALUES (:id, :org_id, :name, :api_key_hash, :retention_days)
            """
        ),
        {
            "id": project_id,
            "org_id": org_id,
            "name": "Access Test Project",
            "api_key_hash": api_key_hash,
            "retention_days": 90,
        },
    )
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
            "role": org_role,
        },
    )
    if project_role is not None:
        await db_session.execute(
            text(
                """
                INSERT INTO project_memberships (id, project_id, user_id, role)
                VALUES (:id, :project_id, :user_id, :role)
                """
            ),
            {
                "id": str(uuid.uuid4()),
                "project_id": project_id,
                "user_id": user_id,
                "role": project_role,
            },
        )

    await db_session.commit()

    return AccessFixture(
        org_id=org_id,
        project_id=project_id,
        user_id=user_id,
        token=create_access_token(user_id, org_id, org_role),
        api_key=api_key,
    )


def auth_headers(fixture: AccessFixture) -> dict[str, str]:
    return {"Authorization": f"Bearer {fixture.token}"}


def alert_rule_body(project_id: str) -> dict[str, object]:
    return {
        "project_id": project_id,
        "name": "Latency guard",
        "metric": "latency_p95",
        "condition": "gt",
        "threshold": "1000",
        "window_minutes": 5,
        "cooldown_minutes": 15,
        "notify_slack_webhook": None,
        "notify_email": None,
    }


@pytest.mark.asyncio
async def test_admin_can_access_org_project_without_membership(
    client: Any, db_session: AsyncSession
) -> None:
    fixture = await create_access_fixture(db_session, org_role="admin")
    headers = auth_headers(fixture)

    metrics = await client.get(
        f"/v1/metrics/overview?project_id={fixture.project_id}", headers=headers
    )
    traces = await client.get(
        f"/v1/traces?project_id={fixture.project_id}", headers=headers
    )
    rules = await client.get(
        f"/v1/alerts/rules?project_id={fixture.project_id}", headers=headers
    )
    settings = await client.get(
        f"/v1/projects/{fixture.project_id}/settings", headers=headers
    )
    api_keys = await client.get(
        f"/v1/projects/{fixture.project_id}/api-keys", headers=headers
    )

    assert metrics.status_code == 200
    assert traces.status_code == 200
    assert rules.status_code == 200
    assert settings.status_code == 200
    assert api_keys.status_code == 200


@pytest.mark.asyncio
async def test_project_member_can_read_and_write_assigned_project(
    client: Any, db_session: AsyncSession
) -> None:
    fixture = await create_access_fixture(
        db_session, org_role="viewer", project_role="member"
    )
    headers = auth_headers(fixture)

    metrics = await client.get(
        f"/v1/metrics/overview?project_id={fixture.project_id}", headers=headers
    )
    traces = await client.get(
        f"/v1/traces?project_id={fixture.project_id}", headers=headers
    )
    rules = await client.get(
        f"/v1/alerts/rules?project_id={fixture.project_id}", headers=headers
    )
    created = await client.post(
        "/v1/alerts/rules",
        json=alert_rule_body(fixture.project_id),
        headers=headers,
    )

    assert metrics.status_code == 200
    assert traces.status_code == 200
    assert rules.status_code == 200
    assert created.status_code == 201


@pytest.mark.asyncio
async def test_project_viewer_can_read_but_not_write_assigned_project(
    client: Any, db_session: AsyncSession
) -> None:
    fixture = await create_access_fixture(
        db_session, org_role="viewer", project_role="viewer"
    )
    headers = auth_headers(fixture)

    metrics = await client.get(
        f"/v1/metrics/overview?project_id={fixture.project_id}", headers=headers
    )
    traces = await client.get(
        f"/v1/traces?project_id={fixture.project_id}", headers=headers
    )
    rules = await client.get(
        f"/v1/alerts/rules?project_id={fixture.project_id}", headers=headers
    )
    created = await client.post(
        "/v1/alerts/rules",
        json=alert_rule_body(fixture.project_id),
        headers=headers,
    )

    assert metrics.status_code == 200
    assert traces.status_code == 200
    assert rules.status_code == 200
    assert created.status_code == 403


@pytest.mark.asyncio
async def test_unassigned_user_cannot_access_project_routes(
    client: Any, db_session: AsyncSession
) -> None:
    fixture = await create_access_fixture(db_session, org_role="member")
    headers = auth_headers(fixture)

    metrics = await client.get(
        f"/v1/metrics/overview?project_id={fixture.project_id}", headers=headers
    )
    traces = await client.get(
        f"/v1/traces?project_id={fixture.project_id}", headers=headers
    )
    rules = await client.get(
        f"/v1/alerts/rules?project_id={fixture.project_id}", headers=headers
    )
    created = await client.post(
        "/v1/alerts/rules",
        json=alert_rule_body(fixture.project_id),
        headers=headers,
    )
    settings = await client.get(
        f"/v1/projects/{fixture.project_id}/settings", headers=headers
    )
    api_keys = await client.get(
        f"/v1/projects/{fixture.project_id}/api-keys", headers=headers
    )

    assert metrics.status_code == 403
    assert traces.status_code == 403
    assert rules.status_code == 403
    assert created.status_code == 403
    assert settings.status_code == 403
    assert api_keys.status_code == 403


@pytest.mark.asyncio
async def test_api_key_access_does_not_require_user_membership(
    client: Any, db_session: AsyncSession
) -> None:
    fixture = await create_access_fixture(db_session, org_role="member")

    metrics = await client.get(
        "/v1/metrics/overview", headers={"X-API-Key": fixture.api_key}
    )
    traces = await client.get("/v1/traces", headers={"X-API-Key": fixture.api_key})

    assert metrics.status_code == 200
    assert traces.status_code == 200
