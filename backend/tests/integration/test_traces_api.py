import pytest
from sqlalchemy import text

from tests.factories import create_test_project, create_test_span, make_span_payload


@pytest.mark.asyncio
async def test_unauthenticated_returns_401(client):
    r = await client.get("/v1/traces")

    assert r.status_code == 401


@pytest.mark.asyncio
async def test_data_isolation_between_projects(client, db_session):
    project_a = await create_test_project(db_session)
    project_b = await create_test_project(db_session)
    span_a = await create_test_span(db_session, project_id=project_a.id, count=1)
    span_b = await create_test_span(db_session, project_id=project_b.id, count=5)

    r = await client.get("/v1/traces", headers={"X-API-Key": project_a.raw_key})

    assert r.status_code == 200
    trace_ids = {item["id"] for item in r.json()["traces"]}
    assert trace_ids == {span_a[0]["trace_id"]}
    assert span_b[0]["trace_id"] not in trace_ids


@pytest.mark.asyncio
async def test_idor_protection_on_trace_detail(client, db_session):
    project_a = await create_test_project(db_session)
    project_b = await create_test_project(db_session)
    span_b = await create_test_span(db_session, project_id=project_b.id, count=5)

    r = await client.get(
        f"/v1/traces/{span_b[0]['trace_id']}", headers={"X-API-Key": project_a.raw_key}
    )

    assert r.status_code == 404


@pytest.mark.asyncio
async def test_trace_detail_returns_parent_span_id(client, db_session):
    project = await create_test_project(db_session)
    spans = await create_test_span(db_session, project_id=project.id, count=2)
    parent_span = spans[0]
    child_span = spans[1]

    await db_session.execute(
        text(
            """
            UPDATE spans
            SET parent_span_id = :parent_span_id
            WHERE id = :child_span_id AND started_at = :started_at
            """
        ),
        {
            "parent_span_id": parent_span["id"],
            "child_span_id": child_span["id"],
            "started_at": child_span["started_at"],
        },
    )
    await db_session.commit()

    r = await client.get(
        f"/v1/traces/{parent_span['trace_id']}",
        headers={"X-API-Key": project.raw_key},
    )

    assert r.status_code == 200
    child = next(span for span in r.json()["spans"] if span["id"] == child_span["id"])
    assert child["parent_span_id"] == parent_span["id"]


@pytest.mark.asyncio
async def test_metrics_overview_isolation_between_projects(client, db_session):
    project_a = await create_test_project(db_session)
    project_b = await create_test_project(db_session)
    await create_test_span(db_session, project_id=project_a.id, count=1)
    await create_test_span(db_session, project_id=project_b.id, count=5)

    r = await client.get(
        "/v1/metrics/overview",
        params={"period": "24h"},
        headers={"X-API-Key": project_a.raw_key},
    )

    assert r.status_code == 200
    assert r.json()["total_spans"] == 1
    assert r.json()["total_tokens"] == 150


@pytest.mark.asyncio
async def test_ingest_rate_limiting(client, db_session):
    from app.core import config as config_module

    project = await create_test_project(db_session)
    headers = {"X-API-Key": project.raw_key}
    payload = {"spans": [make_span_payload()]}

    original_limit = config_module.settings.api_rate_limit_per_minute
    config_module.settings.api_rate_limit_per_minute = 2

    try:
        for _ in range(2):
            await client.post("/v1/ingest", json=payload, headers=headers)

        r = await client.post("/v1/ingest", json=payload, headers=headers)
        assert r.status_code == 429
        assert "Retry-After" in r.headers
    finally:
        config_module.settings.api_rate_limit_per_minute = original_limit


@pytest.mark.asyncio
@pytest.mark.parametrize("field", ["span_id", "trace_id", "parent_span_id"])
async def test_ingest_rejects_invalid_uuid_ids(client, db_session, field):
    project = await create_test_project(db_session)
    span = make_span_payload()
    span[field] = "not-a-uuid"

    r = await client.post(
        "/v1/ingest", json={"spans": [span]}, headers={"X-API-Key": project.raw_key}
    )

    assert r.status_code == 422
