import os
import re
import subprocess
import sys
from datetime import UTC, datetime
from pathlib import Path
from uuid import uuid4

import pytest
from sqlalchemy import text
from sqlalchemy.engine import URL, make_url
from sqlalchemy.ext.asyncio import create_async_engine

pytestmark = pytest.mark.skipif(
    os.getenv("RUN_MIGRATION_SMOKE") != "1",
    reason="set RUN_MIGRATION_SMOKE=1 to run the existing-db migration smoke",
)

BACKEND_DIR = Path(__file__).resolve().parents[2]
BASELINE_REVISION = "e5f6a7b8c9d0"
PROJECT_ID = "11111111-1111-1111-1111-111111111111"
ORG_ID = "22222222-2222-2222-2222-222222222222"
TRACE_ID = "33333333-3333-3333-3333-333333333333"
SPAN_ID = "44444444-4444-4444-4444-444444444444"
STARTED_AT = datetime(2026, 6, 15, 12, 0, tzinfo=UTC)


@pytest.fixture(autouse=True, scope="session")
def patch_app_engine() -> None:
    return None


def _identifier(value: str) -> str:
    if re.fullmatch(r"[a-z_][a-z0-9_]{0,62}", value) is None:
        raise ValueError(f"Unsafe SQL identifier: {value}")
    return f'"{value}"'


def _render_url(url: URL) -> str:
    return url.render_as_string(hide_password=False)


def _base_owner_url() -> URL:
    raw_url = os.getenv("MIGRATION_DATABASE_URL") or os.getenv("DATABASE_URL")
    if raw_url is None:
        pytest.skip("DATABASE_URL or MIGRATION_DATABASE_URL is required")
    return make_url(raw_url)


def _run_alembic_upgrade(target: str, env: dict[str, str]) -> None:
    result = subprocess.run(
        [sys.executable, "-m", "alembic", "upgrade", target],
        cwd=BACKEND_DIR,
        env=env,
        text=True,
        capture_output=True,
        check=False,
    )
    assert result.returncode == 0, (
        f"alembic upgrade {target} failed\n"
        f"stdout:\n{result.stdout}\n"
        f"stderr:\n{result.stderr}"
    )


async def _execute(url: URL, sql: str) -> None:
    engine = create_async_engine(_render_url(url), isolation_level="AUTOCOMMIT")
    try:
        async with engine.connect() as connection:
            await connection.execute(text(sql))
    finally:
        await engine.dispose()


async def _create_database(admin_url: URL, database_name: str) -> None:
    await _execute(admin_url, f"CREATE DATABASE {_identifier(database_name)}")


async def _drop_database(admin_url: URL, database_name: str) -> None:
    quoted_database = _identifier(database_name)
    await _execute(
        admin_url,
        f"""
        SELECT pg_terminate_backend(pid)
        FROM pg_stat_activity
        WHERE datname = '{database_name}' AND pid <> pg_backend_pid()
        """,
    )
    await _execute(admin_url, f"DROP DATABASE IF EXISTS {quoted_database}")


async def _drop_role(admin_url: URL, role_name: str) -> None:
    await _execute(admin_url, f"DROP ROLE IF EXISTS {_identifier(role_name)}")


async def _seed_existing_data(owner_url: URL) -> None:
    engine = create_async_engine(_render_url(owner_url))
    try:
        async with engine.begin() as connection:
            await connection.execute(
                text("SELECT set_config('app.current_project_id', :pid, true)"),
                {"pid": PROJECT_ID},
            )
            await connection.execute(
                text(
                    """
                    INSERT INTO organizations (id, name, slug)
                    VALUES (:org_id, 'Migration Smoke Org', 'migration-smoke-org')
                    """
                ),
                {"org_id": ORG_ID},
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
                    VALUES (
                        :project_id,
                        :org_id,
                        'Migration Smoke Project',
                        'migration-smoke-api-key-hash',
                        90
                    )
                    """
                ),
                {"project_id": PROJECT_ID, "org_id": ORG_ID},
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
                    "trace_id": TRACE_ID,
                    "project_id": PROJECT_ID,
                    "started_at": STARTED_AT,
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
                        payload_s3_key,
                        metadata
                    )
                    VALUES (
                        :span_id,
                        :trace_id,
                        :project_id,
                        NULL,
                        'migration-smoke-span',
                        'openai',
                        'gpt-smoke',
                        1,
                        2,
                        0.000001,
                        12.5,
                        'success',
                        NULL,
                        :started_at,
                        'payloads/11111111-1111-1111-1111-111111111111/44/span.json.gz',
                        '{"fixture": "existing-db"}'::jsonb
                    )
                    """
                ),
                {
                    "span_id": SPAN_ID,
                    "trace_id": TRACE_ID,
                    "project_id": PROJECT_ID,
                    "started_at": STARTED_AT,
                },
            )
    finally:
        await engine.dispose()


async def _verify_head_schema(owner_url: URL) -> None:
    engine = create_async_engine(_render_url(owner_url))
    try:
        async with engine.begin() as connection:
            await connection.execute(
                text("SELECT set_config('app.current_project_id', :pid, true)"),
                {"pid": PROJECT_ID},
            )
            span = (
                await connection.execute(
                    text(
                        """
                        SELECT payload_status, payload_drop_reason
                        FROM spans
                        WHERE id = :span_id AND started_at = :started_at
                        """
                    ),
                    {"span_id": SPAN_ID, "started_at": STARTED_AT},
                )
            ).one()
            assert span.payload_status is None
            assert span.payload_drop_reason is None

            idempotency_table = (
                await connection.execute(
                    text("SELECT to_regclass('idempotency_records')")
                )
            ).scalar_one()
            outbox_table = (
                await connection.execute(text("SELECT to_regclass('outbox_events')"))
            ).scalar_one()
            assert idempotency_table == "idempotency_records"
            assert outbox_table == "outbox_events"

            rls_rows = (
                await connection.execute(
                    text(
                        """
                        SELECT
                            child.relname,
                            child.relrowsecurity,
                            child.relforcerowsecurity
                        FROM pg_inherits
                        JOIN pg_class parent ON parent.oid = pg_inherits.inhparent
                        JOIN pg_class child ON child.oid = pg_inherits.inhrelid
                        WHERE parent.relname IN ('spans', 'traces')
                          AND child.relname IN (
                              'spans_2026_06',
                              'traces_2026_06',
                              'spans_default',
                              'traces_default'
                          )
                        ORDER BY child.relname
                        """
                    )
                )
            ).all()
            assert {row.relname for row in rls_rows} == {
                "spans_2026_06",
                "traces_2026_06",
                "spans_default",
                "traces_default",
            }
            assert all(row.relrowsecurity for row in rls_rows)
            assert all(row.relforcerowsecurity for row in rls_rows)
    finally:
        await engine.dispose()


async def _verify_runtime_role(runtime_url: URL) -> None:
    engine = create_async_engine(_render_url(runtime_url))
    try:
        async with engine.begin() as connection:
            without_context = (
                await connection.execute(text("SELECT COUNT(*) FROM spans"))
            ).scalar_one()
            assert without_context == 0

            await connection.execute(
                text("SELECT set_config('app.current_project_id', :pid, true)"),
                {"pid": PROJECT_ID},
            )
            with_context = (
                await connection.execute(text("SELECT COUNT(*) FROM spans"))
            ).scalar_one()
            assert with_context == 1
    finally:
        await engine.dispose()


@pytest.mark.asyncio
async def test_existing_db_upgrade_preserves_data_and_runtime_rls() -> None:
    suffix = uuid4().hex[:12]
    database_name = f"llmobs_migration_smoke_{suffix}"
    app_role = f"llmobs_smoke_app_{suffix}"
    app_password = f"smoke-password-{suffix}"

    base_owner_url = _base_owner_url()
    admin_url = base_owner_url.set(database="postgres")
    owner_url = base_owner_url.set(database=database_name)
    runtime_url = base_owner_url.set(
        database=database_name,
        username=app_role,
        password=app_password,
    )
    alembic_env = os.environ.copy()
    alembic_env.update(
        {
            "DATABASE_URL": _render_url(runtime_url),
            "MIGRATION_DATABASE_URL": _render_url(owner_url),
            "POSTGRES_APP_USER": app_role,
            "POSTGRES_APP_PASSWORD": app_password,
            "ENVIRONMENT": "test",
            "SECRET_KEY": "migration-smoke-secret-key-for-testing-only-32chars",
        }
    )

    await _create_database(admin_url, database_name)
    try:
        _run_alembic_upgrade(BASELINE_REVISION, alembic_env)
        await _seed_existing_data(owner_url)
        _run_alembic_upgrade("head", alembic_env)

        await _verify_head_schema(owner_url)
        await _verify_runtime_role(runtime_url)
    finally:
        await _drop_database(admin_url, database_name)
        await _drop_role(admin_url, app_role)
