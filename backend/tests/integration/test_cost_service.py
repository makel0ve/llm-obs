import json
from contextlib import asynccontextmanager
from datetime import UTC, datetime
from decimal import Decimal
from typing import Any

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
    def __init__(self, rows: list[dict[str, Any]] | None = None) -> None:
        self.params: list[dict] = []
        self.rows = (
            rows
            if rows is not None
            else [
                _pricing_row(
                    input_cost=Decimal("0.001"),
                    output_cost=Decimal("0.002"),
                    valid_from=datetime(2026, 1, 1, tzinfo=UTC),
                    valid_to=datetime(2026, 7, 1, tzinfo=UTC),
                ),
                _pricing_row(
                    input_cost=Decimal("0.010"),
                    output_cost=Decimal("0.020"),
                    valid_from=datetime(2026, 7, 1, tzinfo=UTC),
                    valid_to=None,
                ),
            ]
        )

    async def execute(
        self, statement: object, params: dict | None = None
    ) -> FakeResult:
        params = params or {}
        self.params.append(params)
        at_time = params["t"]
        matches = [
            row
            for row in self.rows
            if row["provider"] == params["p"]
            and row["model"] == params["m"]
            and row["valid_from"] <= at_time
            and (row["valid_to"] is None or row["valid_to"] > at_time)
        ]
        if not matches:
            return FakeResult(None)

        row = max(matches, key=lambda item: item["valid_from"])
        return FakeResult({"inp": row["input"], "out": row["output"]})


class FakeRedis:
    def __init__(self) -> None:
        self.values: dict[str, str] = {}

    async def get(self, key: str) -> str | None:
        return self.values.get(key)

    async def setex(self, key: str, ttl: int, value: str) -> None:
        self.values[key] = value


def _pricing_row(
    *,
    provider: str = "openai",
    model: str = "gpt-4o",
    input_cost: Decimal,
    output_cost: Decimal,
    valid_from: datetime,
    valid_to: datetime | None,
) -> dict[str, Any]:
    return {
        "provider": provider,
        "model": model,
        "input": input_cost,
        "output": output_cost,
        "valid_from": valid_from,
        "valid_to": valid_to,
    }


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
async def test_pricing_lookup_uses_half_open_historical_boundaries(
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

    before_first_price = await service.calculate(
        provider="openai",
        model="gpt-4o",
        input_tokens=1000,
        output_tokens=1000,
        at_time=datetime(2025, 12, 31, 23, 59, 59, tzinfo=UTC),
    )
    at_first_valid_from = await service.calculate(
        provider="openai",
        model="gpt-4o",
        input_tokens=1000,
        output_tokens=1000,
        at_time=datetime(2026, 1, 1, tzinfo=UTC),
    )
    inside_first_interval = await service.calculate(
        provider="openai",
        model="gpt-4o",
        input_tokens=500,
        output_tokens=500,
        at_time=datetime(2026, 6, 30, 23, 59, 59, tzinfo=UTC),
    )
    at_valid_to_boundary = await service.calculate(
        provider="openai",
        model="gpt-4o",
        input_tokens=1000,
        output_tokens=1000,
        at_time=datetime(2026, 7, 1, tzinfo=UTC),
    )

    assert before_first_price == Decimal("0")
    assert at_first_valid_from == Decimal("0.00300000")
    assert inside_first_interval == Decimal("0.00150000")
    assert at_valid_to_boundary == Decimal("0.03000000")
    assert len(db.params) == 4
    assert len(redis.values) == 3


@pytest.mark.asyncio
async def test_pricing_lookup_uses_span_started_at_for_delayed_delivery(
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
    delayed_span_cost = await service.calculate(
        provider="openai",
        model="gpt-4o",
        input_tokens=1000,
        output_tokens=1000,
        at_time=datetime(2026, 6, 30, 23, 59, 59, tzinfo=UTC),
    )

    assert delayed_span_cost == Decimal("0.00300000")
    assert db.params[-1]["t"] == datetime(2026, 6, 30, 23, 59, 59, tzinfo=UTC)


@pytest.mark.asyncio
async def test_missing_price_returns_zero_and_is_not_cached(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    db = FakeDb(rows=[])
    redis = FakeRedis()

    @asynccontextmanager
    async def fake_get_db():
        yield db

    async def fake_get_redis() -> FakeRedis:
        return redis

    monkeypatch.setattr(cost_module, "get_db", fake_get_db)
    monkeypatch.setattr(cost_module, "get_redis", fake_get_redis)

    service = CostService()
    cost = await service.calculate(
        provider="anthropic",
        model="claude-missing",
        input_tokens=1000,
        output_tokens=1000,
        at_time=datetime(2026, 7, 1, tzinfo=UTC),
    )

    assert cost == Decimal("0")
    assert redis.values == {}


@pytest.mark.asyncio
async def test_overlapping_prices_pick_latest_valid_from(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    db = FakeDb(
        rows=[
            _pricing_row(
                input_cost=Decimal("0.001"),
                output_cost=Decimal("0.002"),
                valid_from=datetime(2026, 1, 1, tzinfo=UTC),
                valid_to=datetime(2026, 8, 1, tzinfo=UTC),
            ),
            _pricing_row(
                input_cost=Decimal("0.010"),
                output_cost=Decimal("0.020"),
                valid_from=datetime(2026, 6, 1, tzinfo=UTC),
                valid_to=None,
            ),
        ]
    )
    redis = FakeRedis()

    @asynccontextmanager
    async def fake_get_db():
        yield db

    async def fake_get_redis() -> FakeRedis:
        return redis

    monkeypatch.setattr(cost_module, "get_db", fake_get_db)
    monkeypatch.setattr(cost_module, "get_redis", fake_get_redis)

    service = CostService()
    cost = await service.calculate(
        provider="openai",
        model="gpt-4o",
        input_tokens=1000,
        output_tokens=1000,
        at_time=datetime(2026, 6, 15, tzinfo=UTC),
    )

    assert cost == Decimal("0.03000000")


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
