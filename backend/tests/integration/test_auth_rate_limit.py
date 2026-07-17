from collections.abc import Callable
from typing import cast

import pytest
from fastapi import HTTPException, Response
from redis.asyncio import Redis

from app.core import config as config_module
from app.core import ratelimit as ratelimit_module
from app.core.ratelimit import AuthRateLimiter


class FakePipeline:
    def __init__(self, redis: "FakeRedis") -> None:
        self.redis = redis
        self.calls: list[Callable[[], object]] = []

    def zremrangebyscore(self, key: str, minimum: float, maximum: float) -> None:
        def call() -> int:
            values = self.redis.values.setdefault(key, [])
            before = len(values)
            self.redis.values[key] = [value for value in values if value > maximum]
            return before - len(self.redis.values[key])

        self.calls.append(call)

    def zadd(self, key: str, mapping: dict[str, float]) -> None:
        def call() -> int:
            values = self.redis.values.setdefault(key, [])
            values.extend(mapping.values())
            return len(mapping)

        self.calls.append(call)

    def zcard(self, key: str) -> None:
        self.calls.append(lambda: len(self.redis.values.setdefault(key, [])))

    def expire(self, key: str, ttl: int) -> None:
        def call() -> bool:
            self.redis.expirations[key] = ttl
            return True

        self.calls.append(call)

    async def execute(self) -> list[object]:
        return [call() for call in self.calls]


class FakeRedis:
    def __init__(self) -> None:
        self.values: dict[str, list[float]] = {}
        self.expirations: dict[str, int] = {}

    def pipeline(self) -> FakePipeline:
        return FakePipeline(self)


@pytest.fixture(autouse=True, scope="session")
def patch_app_engine() -> None:
    return None


@pytest.fixture
def auth_rate_limit_settings(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(config_module.settings, "auth_rate_limit_per_minute", 2)
    monkeypatch.setattr(config_module.settings, "auth_rate_limit_window_seconds", 60)


def _limiter(redis: FakeRedis | None = None) -> AuthRateLimiter:
    return AuthRateLimiter(cast(Redis, redis or FakeRedis()))


@pytest.mark.asyncio
async def test_auth_rate_limiter_allows_attempts_and_sets_headers(
    auth_rate_limit_settings: None,
) -> None:
    limiter = _limiter()
    response = Response()

    await limiter.check(identifier="127.0.0.1", action="login", response=response)
    await limiter.check(identifier="127.0.0.1", action="login", response=response)

    assert response.headers["X-RateLimit-Limit"] == "2"
    assert response.headers["X-RateLimit-Remaining"] == "0"


@pytest.mark.asyncio
async def test_auth_rate_limiter_blocks_after_limit(
    auth_rate_limit_settings: None,
) -> None:
    limiter = _limiter()
    response = Response()

    await limiter.check(identifier="127.0.0.1", action="login", response=response)
    await limiter.check(identifier="127.0.0.1", action="login", response=response)

    with pytest.raises(HTTPException) as exc_info:
        await limiter.check(identifier="127.0.0.1", action="login", response=response)

    assert exc_info.value.status_code == 429
    assert exc_info.value.detail == {"error": "rate_limit_exceeded", "limit": 2}
    assert exc_info.value.headers == {
        "Retry-After": "60",
        "X-RateLimit-Limit": "2",
        "X-RateLimit-Remaining": "0",
    }


@pytest.mark.asyncio
async def test_auth_rate_limiter_resets_after_window(
    monkeypatch: pytest.MonkeyPatch,
    auth_rate_limit_settings: None,
) -> None:
    redis = FakeRedis()
    limiter = _limiter(redis)
    response = Response()
    current_time = 1000.0
    monkeypatch.setattr(ratelimit_module.time, "time", lambda: current_time)

    await limiter.check(identifier="127.0.0.1", action="register", response=response)
    await limiter.check(identifier="127.0.0.1", action="register", response=response)

    current_time += 61
    await limiter.check(identifier="127.0.0.1", action="register", response=response)

    assert response.headers["X-RateLimit-Remaining"] == "1"
