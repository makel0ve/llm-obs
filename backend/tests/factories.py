import hashlib
import json
import uuid
from datetime import UTC, datetime

import pytest
from httpx import ASGITransport, AsyncClient
from sqlalchemy import text
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

import app.core.db as db_module
import app.core.redis as redis_module
from app.core.config import settings
from app.main import app
from app.models import Base


@pytest.fixture(scope="session")
async def test_engine():
    engine = create_async_engine(
        settings.database_url.get_secret_value(),
        echo=False,
        pool_pre_ping=True,
    )
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    yield engine
    await engine.dispose()


@pytest.fixture(autouse=True, scope="session")
async def patch_app_engine(test_engine):
    original_engine = db_module.engine
    original_factory = db_module.session_factory
    db_module.engine = test_engine
    db_module.session_factory = async_sessionmaker(test_engine, expire_on_commit=False)
    yield
    db_module.engine = original_engine
    db_module.session_factory = original_factory


@pytest.fixture(autouse=True, scope="session")
async def reset_redis():
    redis_module._redis_client = None
    yield
    if redis_module._redis_client is not None:
        await redis_module._redis_client.aclose()
        redis_module._redis_client = None


@pytest.fixture
async def db_session(test_engine):
    factory = async_sessionmaker(test_engine, expire_on_commit=False)
    async with factory() as session:
        yield session
        await session.rollback()


@pytest.fixture(scope="session")
async def client():
    async with AsyncClient(
        transport=ASGITransport(app=app), base_url="http://test"
    ) as c:
        yield c


class TestProject:
    def __init__(self, id: str, raw_key: str, api_key_hash: str):
        self.id = id
        self.raw_key = raw_key
        self.api_key_hash = api_key_hash


async def create_test_project(db_session) -> TestProject:
    org_id = str(uuid.uuid4())
    project_id = str(uuid.uuid4())
    raw_key = f"llmobs_test_{uuid.uuid4().hex}"
    key_hash = hashlib.sha256(raw_key.encode()).hexdigest()

    await db_session.execute(
        text("INSERT INTO organizations (id, name, slug) VALUES (:id, :name, :slug)"),
        {"id": org_id, "name": "Test Org", "slug": f"test-org-{org_id[:8]}"},
    )

    await db_session.execute(
        text(
            """
        INSERT INTO projects (id, org_id, name, api_key_hash, retention_days)
        VALUES (:id, :org_id, :name, :hash, :retention)
        """
        ),
        {
            "id": project_id,
            "org_id": org_id,
            "name": f"Test Project {project_id[:8]}",
            "hash": key_hash,
            "retention": 90,
        },
    )

    await db_session.commit()
    return TestProject(id=project_id, raw_key=raw_key, api_key_hash=key_hash)


async def create_test_span(db_session, project_id: str, count: int = 1) -> list[dict]:
    spans = []
    trace_id = str(uuid.uuid4())

    for _ in range(count):
        span_id = str(uuid.uuid4())
        started_at = datetime.now(UTC)

        await db_session.execute(
            text(
                """
            INSERT INTO spans (
                id, trace_id, project_id, name, provider, model,
                input_tokens, output_tokens, cost_usd, latency_ms,
                status, started_at, metadata
            ) VALUES (
                :id, :trace_id, :project_id, :name, :provider, :model,
                :input_tokens, :output_tokens, :cost_usd, :latency_ms,
                :status, :started_at, :metadata
            )
            """
            ),
            {
                "id": span_id,
                "trace_id": trace_id,
                "project_id": project_id,
                "name": "test.span",
                "provider": "openai",
                "model": "gpt-4o",
                "input_tokens": 100,
                "output_tokens": 50,
                "cost_usd": "0.00100000",
                "latency_ms": 500.0,
                "status": "ok",
                "started_at": started_at,
                "metadata": json.dumps({}),
            },
        )

        spans.append(
            {
                "id": span_id,
                "trace_id": trace_id,
                "project_id": project_id,
                "started_at": started_at,
            }
        )

    await db_session.commit()

    return spans


def make_span_payload() -> dict:
    return {
        "span_id": str(uuid.uuid4()),
        "trace_id": str(uuid.uuid4()),
        "name": "test.span",
        "provider": "openai",
        "model": "gpt-4o",
        "input_messages": [{"role": "user", "content": "test"}],
        "input_tokens": 100,
        "output_tokens": 50,
        "latency_ms": 500.0,
        "started_at": datetime.now(UTC).isoformat(),
    }
