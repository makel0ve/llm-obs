from datetime import UTC, datetime, timedelta

import pytest
from fastapi import HTTPException

from app.api.v1 import health as health_api
from app.workers import health as worker_health


@pytest.fixture(autouse=True, scope="session")
def patch_app_engine():
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


@pytest.mark.asyncio
async def test_record_worker_heartbeat_writes_redis_key(monkeypatch):
    redis = FakeRedis()

    async def fake_get_redis() -> FakeRedis:
        return redis

    monkeypatch.setattr(worker_health, "get_redis", fake_get_redis)
    monkeypatch.setattr(worker_health.settings, "worker_heartbeat_ttl_seconds", 300)

    seen_at = await worker_health.write_worker_heartbeat()

    assert redis.set_calls == [
        (worker_health.WORKER_HEARTBEAT_KEY, seen_at, 300),
    ]
    assert datetime.fromisoformat(seen_at).tzinfo is not None


@pytest.mark.asyncio
async def test_worker_health_returns_ok_for_fresh_heartbeat(monkeypatch):
    redis = FakeRedis(datetime.now(UTC).isoformat())

    async def fake_get_redis() -> FakeRedis:
        return redis

    monkeypatch.setattr(health_api, "get_redis", fake_get_redis)
    monkeypatch.setattr(health_api.settings, "worker_heartbeat_max_age_seconds", 180)

    response = await health_api.worker_health()

    assert response["status"] == "ok"
    assert response["worker"]["age_seconds"] <= 180


@pytest.mark.asyncio
async def test_worker_health_raises_503_when_heartbeat_missing(monkeypatch):
    redis = FakeRedis()

    async def fake_get_redis() -> FakeRedis:
        return redis

    monkeypatch.setattr(health_api, "get_redis", fake_get_redis)

    with pytest.raises(HTTPException) as exc:
        await health_api.worker_health()

    assert exc.value.status_code == 503
    assert exc.value.detail["status"] == "missing"


@pytest.mark.asyncio
async def test_worker_health_raises_503_when_heartbeat_stale(monkeypatch):
    old_seen_at = (datetime.now(UTC) - timedelta(seconds=240)).isoformat()
    redis = FakeRedis(old_seen_at)

    async def fake_get_redis() -> FakeRedis:
        return redis

    monkeypatch.setattr(health_api, "get_redis", fake_get_redis)
    monkeypatch.setattr(health_api.settings, "worker_heartbeat_max_age_seconds", 180)

    with pytest.raises(HTTPException) as exc:
        await health_api.worker_health()

    assert exc.value.status_code == 503
    assert exc.value.detail["status"] == "stale"
    assert exc.value.detail["worker"]["last_seen"] == old_seen_at
