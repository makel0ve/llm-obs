import json
from contextlib import asynccontextmanager
from datetime import UTC, datetime
from decimal import Decimal

import pytest

from app.services import cost as cost_module
from app.services.cost import CostService


class FakeResult:
    def __init__(self, row: dict | None) -> None:
        self._row = row

    def mappings(self) -> "FakeResult":
        return self

    def one_or_none(self) -> dict | None:
        return self._row


class FakeDb:
    def __init__(self) -> None:
        self.params: list[dict] = []

    async def execute(
        self, statement: object, params: dict | None = None
    ) -> FakeResult:
        params = params or {}
        self.params.append(params)
        at_time = params["t"]
        if at_time < datetime(2026, 7, 1, tzinfo=UTC):
            return FakeResult({"inp": Decimal("0.001"), "out": Decimal("0.002")})

        return FakeResult({"inp": Decimal("0.010"), "out": Decimal("0.020")})


class FakeRedis:
    def __init__(self) -> None:
        self.values: dict[str, str] = {}

    async def get(self, key: str) -> str | None:
        return self.values.get(key)

    async def setex(self, key: str, ttl: int, value: str) -> None:
        self.values[key] = value


@pytest.fixture(autouse=True, scope="session")
def patch_app_engine() -> None:
    return None


@pytest.mark.asyncio
async def test_pricing_cache_includes_historical_lookup_time(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    db = FakeDb()
    redis = FakeRedis()

    @asynccontextmanager
    async def fake_get_db():
        yield db

    async def fake_get_redis() -> FakeRedis:
        return redis

    monkeypatch.setattr(cost_module, "get_db", fake_get_db)
    monkeypatch.setattr(cost_module, "get_redis", fake_get_redis)

    service = CostService()
    old_cost = await service.calculate(
        provider="openai",
        model="gpt-4o",
        input_tokens=1000,
        output_tokens=1000,
        at_time=datetime(2026, 6, 1, tzinfo=UTC),
    )
    new_cost = await service.calculate(
        provider="openai",
        model="gpt-4o",
        input_tokens=1000,
        output_tokens=1000,
        at_time=datetime(2026, 8, 1, tzinfo=UTC),
    )

    assert old_cost == Decimal("0.00300000")
    assert new_cost == Decimal("0.03000000")
    assert len(db.params) == 2
    assert len(redis.values) == 2
    assert all(key.startswith("pricing:openai:gpt-4o:") for key in redis.values)


@pytest.mark.asyncio
async def test_pricing_cache_reuses_same_historical_lookup_time(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    db = FakeDb()
    redis = FakeRedis()
    at_time = datetime(2026, 6, 1, tzinfo=UTC)

    @asynccontextmanager
    async def fake_get_db():
        yield db

    async def fake_get_redis() -> FakeRedis:
        return redis

    monkeypatch.setattr(cost_module, "get_db", fake_get_db)
    monkeypatch.setattr(cost_module, "get_redis", fake_get_redis)

    service = CostService()
    first = await service._get_pricing("openai", "gpt-4o", at_time)
    second = await service._get_pricing("openai", "gpt-4o", at_time)

    assert first == second == {"input": "0.001", "output": "0.002"}
    assert len(db.params) == 1
    assert json.loads(next(iter(redis.values.values()))) == first
