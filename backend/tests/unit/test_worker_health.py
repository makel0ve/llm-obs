from collections.abc import AsyncIterator, Iterator
from contextlib import asynccontextmanager
from datetime import UTC, datetime, timedelta
from typing import Any, cast

import pytest
from fastapi import HTTPException

from app.api.v1 import health as health_api
from app.workers import health as worker_health


@pytest.fixture(autouse=True, scope="session")
def patch_app_engine() -> Iterator[None]:
    yield


class FakeRedis:
    def __init__(self, value: str | None = None) -> None:
        self.value = value
        self.set_calls: list[tuple[str, str, int | None]] = []

    async def get(self, key: str) -> str | None:
        assert key == worker_health.WORKER_HEARTBEAT_KEY
        return self.value

    async def set(self, key: str, value: str, ex: int | None = None) -> None:
        self.set_calls.append((key, value, ex))
        self.value = value

    async def ping(self) -> bool:
        return True


class FakeDb:
    async def execute(self, statement: object) -> None:
        return None


class FailingDb:
    async def execute(self, statement: object) -> None:
        raise RuntimeError("postgres password=secret host=db.internal")


@pytest.mark.asyncio
async def test_record_worker_heartbeat_writes_redis_key(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    redis = FakeRedis()

    async def fake_get_redis() -> FakeRedis:
        return redis

    monkeypatch.setattr(worker_health, "get_redis", fake_get_redis)
    monkeypatch.setattr(
        "app.workers.health.settings.worker_heartbeat_ttl_seconds",
        300,
    )

    seen_at = await worker_health.write_worker_heartbeat()

    assert redis.set_calls == [
        (worker_health.WORKER_HEARTBEAT_KEY, seen_at, 300),
    ]
    assert datetime.fromisoformat(seen_at).tzinfo is not None


@pytest.mark.asyncio
async def test_readiness_returns_sanitized_dependency_status(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    redis = FakeRedis()

    @asynccontextmanager
    async def fake_get_db() -> AsyncIterator[FakeDb]:
        yield FakeDb()

    async def fake_get_redis() -> FakeRedis:
        return redis

    monkeypatch.setattr(health_api, "get_db", fake_get_db)
    monkeypatch.setattr(health_api, "get_redis", fake_get_redis)

    response = await health_api.readiness()

    assert response == {
        "status": "ready",
        "checks": {"postgres": "ok", "redis": "ok"},
    }


@pytest.mark.asyncio
async def test_readiness_redacts_dependency_exception_text(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    redis = FakeRedis()

    @asynccontextmanager
    async def fake_get_db() -> AsyncIterator[FailingDb]:
        yield FailingDb()

    async def fake_get_redis() -> FakeRedis:
        return redis

    monkeypatch.setattr(health_api, "get_db", fake_get_db)
    monkeypatch.setattr(health_api, "get_redis", fake_get_redis)

    with pytest.raises(HTTPException) as exc:
        await health_api.readiness()

    assert exc.value.status_code == 503
    detail = cast(dict[str, str], exc.value.detail)
    assert detail == {"postgres": "error", "redis": "ok"}
    assert "secret" not in str(detail)
    assert "db.internal" not in str(detail)


@pytest.mark.asyncio
async def test_worker_health_returns_ok_for_fresh_heartbeat(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    redis = FakeRedis(datetime.now(UTC).isoformat())

    async def fake_get_redis() -> FakeRedis:
        return redis

    monkeypatch.setattr(health_api, "get_redis", fake_get_redis)
    monkeypatch.setattr(
        "app.api.v1.health.settings.worker_heartbeat_max_age_seconds",
        180,
    )

    response = await health_api.worker_health()
    worker = cast(dict[str, Any], response["worker"])

    assert response["status"] == "ok"
    assert worker["age_seconds"] <= 180


@pytest.mark.asyncio
async def test_worker_health_raises_503_when_heartbeat_missing(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    redis = FakeRedis()

    async def fake_get_redis() -> FakeRedis:
        return redis

    monkeypatch.setattr(health_api, "get_redis", fake_get_redis)

    with pytest.raises(HTTPException) as exc:
        await health_api.worker_health()

    assert exc.value.status_code == 503
    detail = cast(dict[str, Any], exc.value.detail)
    assert detail["status"] == "missing"


@pytest.mark.asyncio
async def test_worker_health_raises_503_when_heartbeat_stale(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    old_seen_at = (datetime.now(UTC) - timedelta(seconds=240)).isoformat()
    redis = FakeRedis(old_seen_at)

    async def fake_get_redis() -> FakeRedis:
        return redis

    monkeypatch.setattr(health_api, "get_redis", fake_get_redis)
    monkeypatch.setattr(
        "app.api.v1.health.settings.worker_heartbeat_max_age_seconds",
        180,
    )

    with pytest.raises(HTTPException) as exc:
        await health_api.worker_health()

    assert exc.value.status_code == 503
    detail = cast(dict[str, Any], exc.value.detail)
    worker = cast(dict[str, Any], detail["worker"])
    assert detail["status"] == "stale"
    assert worker["last_seen"] == old_seen_at


@pytest.mark.asyncio
async def test_worker_health_redacts_redis_exception_text(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    async def fake_get_redis() -> FakeRedis:
        raise RuntimeError("redis password=secret host=redis.internal")

    monkeypatch.setattr(health_api, "get_redis", fake_get_redis)

    with pytest.raises(HTTPException) as exc:
        await health_api.worker_health()

    assert exc.value.status_code == 503
    detail = cast(dict[str, str], exc.value.detail)
    assert detail == {"status": "error", "worker": "redis error"}
    assert "secret" not in str(detail)
    assert "redis.internal" not in str(detail)
