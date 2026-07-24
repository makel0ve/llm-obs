import os
from dataclasses import dataclass
from datetime import UTC, datetime
from uuid import uuid4

import pytest
from sqlalchemy import text
from sqlalchemy.engine import make_url
from sqlalchemy.ext.asyncio import AsyncEngine, create_async_engine

from app.core.config import settings

pytestmark = pytest.mark.skipif(
    os.getenv("RUN_RUNTIME_RLS_TESTS") != "1",
    reason="set RUN_RUNTIME_RLS_TESTS=1 to run runtime-role RLS checks",
)


@pytest.fixture(autouse=True, scope="session")
def patch_app_engine() -> None:
    return None


@dataclass(frozen=True)
class RLSFixture:
    org_id: str
    project_a_id: str
    project_b_id: str
    trace_a_id: str
    trace_b_id: str
    span_a_id: str
    span_b_id: str
    started_at: datetime


def _render_url(raw_url: str) -> str:
    return make_url(raw_url).render_as_string(hide_password=False)


def _owner_url() -> str:
    return _render_url(settings.effective_migration_database_url.get_secret_value())


def _runtime_url() -> str:
    return _render_url(settings.database_url.get_secret_value())


def _create_engine(url: str) -> AsyncEngine:
    return create_async_engine(url, connect_args={"timeout": 5})


async def _seed_tenant_rows(owner_url: str) -> RLSFixture:
    fixture = RLSFixture(
        org_id=str(uuid4()),
        project_a_id=str(uuid4()),
        project_b_id=str(uuid4()),
        trace_a_id=str(uuid4()),
        trace_b_id=str(uuid4()),
        span_a_id=str(uuid4()),
        span_b_id=str(uuid4()),
        started_at=datetime(2026, 7, 24, 12, 0, tzinfo=UTC),
    )
    engine = _create_engine(owner_url)
    try:
        async with engine.begin() as connection:
            await connection.execute(
                text(
                    """
                    INSERT INTO organizations (id, name, slug)
                    VALUES (:org_id, 'Runtime RLS CI Org', :slug)
                    """
                ),
                {
                    "org_id": fixture.org_id,
                    "slug": f"runtime-rls-ci-{fixture.org_id[:8]}",
                },
            )
            await connection.execute(
                text(
                    """
                    INSERT INTO projects (
                        id,
                        org_id,
                        name,
                        api_key_hash,
                        retention_days
                    )
                    VALUES
                        (:project_a_id, :org_id, 'Runtime RLS Project A', :hash_a, 90),
                        (:project_b_id, :org_id, 'Runtime RLS Project B', :hash_b, 90)
                    """
                ),
                {
                    "org_id": fixture.org_id,
                    "project_a_id": fixture.project_a_id,
                    "project_b_id": fixture.project_b_id,
                    "hash_a": f"runtime-rls-hash-{fixture.project_a_id}",
                    "hash_b": f"runtime-rls-hash-{fixture.project_b_id}",
                },
            )
            for project_id, trace_id, span_id, span_name in (
                (
                    fixture.project_a_id,
                    fixture.trace_a_id,
                    fixture.span_a_id,
                    "runtime.rls.project_a",
                ),
                (
                    fixture.project_b_id,
                    fixture.trace_b_id,
                    fixture.span_b_id,
                    "runtime.rls.project_b",
                ),
            ):
                await connection.execute(
                    text("SELECT set_config('app.current_project_id', :pid, true)"),
                    {"pid": project_id},
                )
                await connection.execute(
                    text(
                        """
                        INSERT INTO traces (
                            id,
                            project_id,
                            started_at,
                            ended_at,
                            total_tokens,
                            total_cost_usd,
                            span_count,
                            status
                        )
                        VALUES (
                            :trace_id,
                            :project_id,
                            :started_at,
                            :started_at,
                            3,
                            0.000001,
                            1,
                            'success'
                        )
                        """
                    ),
                    {
                        "trace_id": trace_id,
                        "project_id": project_id,
                        "started_at": fixture.started_at,
                    },
                )
                await connection.execute(
                    text(
                        """
                        INSERT INTO spans (
                            id,
                            trace_id,
                            project_id,
                            parent_span_id,
                            name,
                            provider,
                            model,
                            input_tokens,
                            output_tokens,
                            cost_usd,
                            latency_ms,
                            status,
                            error,
                            started_at,
                            metadata
                        )
                        VALUES (
                            :span_id,
                            :trace_id,
                            :project_id,
                            NULL,
                            :name,
                            'openai',
                            'gpt-4o',
                            1,
                            2,
                            0.000001,
                            12.5,
                            'success',
                            NULL,
                            :started_at,
                            '{}'::jsonb
                        )
                        """
                    ),
                    {
                        "span_id": span_id,
                        "trace_id": trace_id,
                        "project_id": project_id,
                        "name": span_name,
                        "started_at": fixture.started_at,
                    },
                )
        return fixture
    finally:
        await engine.dispose()


async def _cleanup_tenant_rows(owner_url: str, fixture: RLSFixture) -> None:
    engine = _create_engine(owner_url)
    try:
        async with engine.begin() as connection:
            await connection.execute(
                text("DELETE FROM spans WHERE project_id IN (:project_a, :project_b)"),
                {
                    "project_a": fixture.project_a_id,
                    "project_b": fixture.project_b_id,
                },
            )
            await connection.execute(
                text("DELETE FROM traces WHERE project_id IN (:project_a, :project_b)"),
                {
                    "project_a": fixture.project_a_id,
                    "project_b": fixture.project_b_id,
                },
            )
            await connection.execute(
                text("DELETE FROM projects WHERE org_id = :org_id"),
                {"org_id": fixture.org_id},
            )
            await connection.execute(
                text("DELETE FROM organizations WHERE id = :org_id"),
                {"org_id": fixture.org_id},
            )
    finally:
        await engine.dispose()


async def test_runtime_role_enforces_physical_project_rls() -> None:
    owner_url = _owner_url()
    runtime_url = _runtime_url()
    assert owner_url != runtime_url

    fixture = await _seed_tenant_rows(owner_url)
    engine = _create_engine(runtime_url)
    try:
        async with engine.begin() as connection:
            role = (
                await connection.execute(
                    text(
                        """
                        SELECT rolname, rolsuper, rolbypassrls
                        FROM pg_roles
                        WHERE rolname = current_user
                        """
                    )
                )
            ).one()
            assert role.rolsuper is False
            assert role.rolbypassrls is False

            spans_without_context = (
                await connection.execute(text("SELECT COUNT(*) FROM spans"))
            ).scalar_one()
            traces_without_context = (
                await connection.execute(text("SELECT COUNT(*) FROM traces"))
            ).scalar_one()
            assert spans_without_context == 0
            assert traces_without_context == 0

            await connection.execute(
                text("SELECT set_config('app.current_project_id', :pid, true)"),
                {"pid": fixture.project_a_id},
            )
            visible_spans = (
                await connection.execute(
                    text("SELECT project_id::text, id::text FROM spans ORDER BY id")
                )
            ).all()
            visible_traces = (
                await connection.execute(
                    text("SELECT project_id::text, id::text FROM traces ORDER BY id")
                )
            ).all()
            assert [tuple(row) for row in visible_spans] == [
                (fixture.project_a_id, fixture.span_a_id)
            ]
            assert [tuple(row) for row in visible_traces] == [
                (fixture.project_a_id, fixture.trace_a_id)
            ]
    finally:
        await engine.dispose()
        await _cleanup_tenant_rows(owner_url, fixture)


async def test_trace_span_parent_and_child_partitions_force_rls() -> None:
    owner_url = _owner_url()
    engine = _create_engine(owner_url)
    try:
        async with engine.begin() as connection:
            rows = (
                await connection.execute(
                    text(
                        """
                        SELECT
                            relname,
                            relrowsecurity,
                            relforcerowsecurity,
                            false AS is_child
                        FROM pg_class
                        WHERE relname IN ('spans', 'traces')
                        UNION ALL
                        SELECT
                            child.relname,
                            child.relrowsecurity,
                            child.relforcerowsecurity,
                            true AS is_child
                        FROM pg_inherits
                        JOIN pg_class parent ON parent.oid = pg_inherits.inhparent
                        JOIN pg_class child ON child.oid = pg_inherits.inhrelid
                        WHERE parent.relname IN ('spans', 'traces')
                        ORDER BY relname
                        """
                    )
                )
            ).all()
    finally:
        await engine.dispose()

    assert {row.relname for row in rows} >= {"spans", "traces"}
    assert any(row.is_child for row in rows)
    assert all(row.relrowsecurity for row in rows)
    assert all(row.relforcerowsecurity for row in rows)
