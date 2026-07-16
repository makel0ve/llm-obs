from datetime import UTC, datetime, timedelta
from uuid import UUID, uuid4

import pytest
from sqlalchemy import text

from app.workers.process_span import ensure_trace_row, update_trace_aggregates
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
        text("SELECT set_config('app.current_project_id', :project_id, true)"),
        {"project_id": project.id},
    )
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
async def test_trace_aggregate_ended_at_uses_span_end_times(db_session):
    project = await create_test_project(db_session)
    trace_id = str(uuid4())
    trace_started_at = datetime(2026, 7, 16, 10, 0, 0, tzinfo=UTC)
    long_span_started_at = trace_started_at
    short_span_started_at = trace_started_at + timedelta(seconds=5)
    expected_ended_at = trace_started_at + timedelta(seconds=10)

    await db_session.execute(
        text("SELECT set_config('app.current_project_id', :project_id, true)"),
        {"project_id": project.id},
    )
    await db_session.execute(
        text(
            """
            INSERT INTO traces (
                id, project_id, started_at, ended_at, total_tokens,
                total_cost_usd, span_count, status
            ) VALUES (
                :id, :project_id, :started_at, :ended_at, 0, 0, 0, 'ok'
            )
            """
        ),
        {
            "id": trace_id,
            "project_id": project.id,
            "started_at": trace_started_at,
            "ended_at": trace_started_at,
        },
    )
    await db_session.execute(
        text(
            """
            INSERT INTO spans (
                id, trace_id, project_id, name, provider, model,
                input_tokens, output_tokens, cost_usd, latency_ms,
                status, started_at, metadata
            ) VALUES
            (
                :long_span_id, :trace_id, :project_id, 'long', 'openai', 'gpt-4o',
                10, 5, 0, 10000, 'ok', :long_span_started_at, '{}'
            ),
            (
                :short_span_id, :trace_id, :project_id, 'short', 'openai', 'gpt-4o',
                1, 1, 0, 1000, 'ok', :short_span_started_at, '{}'
            )
            """
        ),
        {
            "long_span_id": str(uuid4()),
            "short_span_id": str(uuid4()),
            "trace_id": trace_id,
            "project_id": project.id,
            "long_span_started_at": long_span_started_at,
            "short_span_started_at": short_span_started_at,
        },
    )
    await db_session.commit()

    await update_trace_aggregates.original_func(
        project_id=project.id,
        trace_id=trace_id,
        started_at=trace_started_at.isoformat(),
    )

    await db_session.execute(
        text("SELECT set_config('app.current_project_id', :project_id, true)"),
        {"project_id": project.id},
    )
    result = await db_session.execute(
        text(
            """
            SELECT ended_at, total_tokens, span_count
            FROM traces
            WHERE id = :trace_id
                AND project_id = :project_id
                AND started_at = :started_at
            """
        ),
        {
            "trace_id": trace_id,
            "project_id": project.id,
            "started_at": trace_started_at,
        },
    )
    row = result.mappings().one()

    assert row["ended_at"] == expected_ended_at
    assert row["total_tokens"] == 17
    assert row["span_count"] == 2


@pytest.mark.asyncio
async def test_trace_identity_uses_earliest_started_at_for_out_of_order_batches(
    db_session,
):
    project = await create_test_project(db_session)
    trace_id = uuid4()
    project_id = UUID(project.id)
    newer_started_at = datetime(2026, 7, 16, 10, 5, 0, tzinfo=UTC)
    older_started_at = datetime(2026, 7, 16, 10, 0, 0, tzinfo=UTC)

    await db_session.execute(
        text("SELECT set_config('app.current_project_id', :project_id, true)"),
        {"project_id": project.id},
    )

    first_start = await ensure_trace_row(
        db=db_session,
        project_id=project_id,
        trace_id=trace_id,
        started_at=newer_started_at,
        status="ok",
    )
    second_start = await ensure_trace_row(
        db=db_session,
        project_id=project_id,
        trace_id=trace_id,
        started_at=older_started_at,
        status="ok",
    )
    await db_session.commit()

    await db_session.execute(
        text("SELECT set_config('app.current_project_id', :project_id, true)"),
        {"project_id": project.id},
    )
    result = await db_session.execute(
        text(
            """
            SELECT started_at
            FROM traces
            WHERE project_id = :project_id AND id = :trace_id
            ORDER BY started_at ASC
            """
        ),
        {"project_id": project_id, "trace_id": trace_id},
    )
    rows = result.mappings().all()

    assert first_start == newer_started_at
    assert second_start == older_started_at
    assert [row["started_at"] for row in rows] == [older_started_at]


@pytest.mark.asyncio
async def test_trace_identity_repeated_batch_keeps_single_trace_row(db_session):
    project = await create_test_project(db_session)
    trace_id = uuid4()
    project_id = UUID(project.id)
    started_at = datetime(2026, 7, 16, 10, 0, 0, tzinfo=UTC)

    await db_session.execute(
        text("SELECT set_config('app.current_project_id', :project_id, true)"),
        {"project_id": project.id},
    )

    first_start = await ensure_trace_row(
        db=db_session,
        project_id=project_id,
        trace_id=trace_id,
        started_at=started_at,
        status="ok",
    )
    second_start = await ensure_trace_row(
        db=db_session,
        project_id=project_id,
        trace_id=trace_id,
        started_at=started_at,
        status="ok",
    )
    await db_session.commit()

    await db_session.execute(
        text("SELECT set_config('app.current_project_id', :project_id, true)"),
        {"project_id": project.id},
    )
    result = await db_session.execute(
        text(
            """
            SELECT COUNT(*) AS trace_count, MIN(started_at) AS started_at
            FROM traces
            WHERE project_id = :project_id AND id = :trace_id
            """
        ),
        {"project_id": project_id, "trace_id": trace_id},
    )
    row = result.mappings().one()

    assert first_start == started_at
    assert second_start == started_at
    assert row["trace_count"] == 1
    assert row["started_at"] == started_at


@pytest.mark.asyncio
async def test_trace_cursor_handles_timestamp_delimiters(client, db_session):
    project = await create_test_project(db_session)
    await create_test_span(db_session, project_id=project.id, count=1)
    await create_test_span(db_session, project_id=project.id, count=1)

    first_page = await client.get(
        "/v1/traces",
        params={"page_size": 1},
        headers={"X-API-Key": project.raw_key},
    )

    assert first_page.status_code == 200
    first_payload = first_page.json()
    assert first_payload["has_more"] is True
    assert first_payload["next_cursor"]

    second_page = await client.get(
        "/v1/traces",
        params={"page_size": 1, "cursor": first_payload["next_cursor"]},
        headers={"X-API-Key": project.raw_key},
    )

    assert second_page.status_code == 200
    second_payload = second_page.json()
    assert len(second_payload["traces"]) == 1
    assert second_payload["traces"][0]["id"] != first_payload["traces"][0]["id"]


@pytest.mark.asyncio
async def test_trace_cursor_rejects_invalid_cursor(client, db_session):
    project = await create_test_project(db_session)

    response = await client.get(
        "/v1/traces",
        params={"cursor": "not-a-valid-cursor"},
        headers={"X-API-Key": project.raw_key},
    )

    assert response.status_code == 400
    assert response.json()["detail"] == "Invalid pagination cursor"


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
