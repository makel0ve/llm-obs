from contextlib import asynccontextmanager
from datetime import UTC, datetime
from decimal import Decimal
from uuid import uuid4

import pytest
from fastapi import HTTPException

from app.api.v1 import pricing as pricing_api
from app.api.v1.pricing import (
    create_pricing,
    end_pricing,
    list_pricing,
    update_pricing,
)
from app.schemas.pricing import PricingCreate, PricingEndDate, PricingUpdate


class FakeResult:
    def __init__(self, rows=None, row=None):
        self._rows = rows or []
        self._row = row

    def mappings(self):
        return self

    def all(self):
        return self._rows

    def one(self):
        if self._row is None:
            raise AssertionError("expected row")
        return self._row

    def one_or_none(self):
        return self._row


class FakeTransaction:
    async def __aenter__(self):
        return self

    async def __aexit__(self, exc_type, exc, tb):
        return False


class FakeDb:
    def __init__(self):
        self.params = []
        self.committed = False

    def begin(self):
        return FakeTransaction()

    async def execute(self, statement, params=None):
        sql = str(statement)
        self.params.append(params or {})

        if "SELECT id, provider" in sql:
            return FakeResult(rows=[_pricing_row()])

        if "INSERT INTO model_pricing" in sql:
            return FakeResult(
                row=_pricing_row(provider=params["provider"], model=params["model"])
            )

        if "UPDATE model_pricing SET" in sql and "RETURNING id" in sql:
            row = _pricing_row()
            if params and "valid_from" in params:
                row = {**row, "valid_from": params["valid_from"]}
            if params and "valid_to" in params:
                row = {**row, "valid_to": params["valid_to"]}
            return FakeResult(row=row)

        return FakeResult()

    async def commit(self):
        self.committed = True


class FakeRedis:
    def __init__(self):
        self.deleted = []

    async def delete(self, key):
        self.deleted.append(key)


@pytest.fixture(autouse=True, scope="session")
def patch_app_engine():
    yield


@pytest.fixture
def fake_db():
    return FakeDb()


@pytest.fixture
def fake_redis():
    return FakeRedis()


@pytest.fixture(autouse=True)
def patch_dependencies(monkeypatch, fake_db, fake_redis):
    @asynccontextmanager
    async def fake_get_db():
        yield fake_db

    async def fake_get_redis():
        return fake_redis

    monkeypatch.setattr(pricing_api, "get_db", fake_get_db)
    monkeypatch.setattr(pricing_api, "get_redis", fake_get_redis)


def _admin():
    return {"sub": str(uuid4()), "org_id": str(uuid4()), "role": "admin"}


def _member():
    return {"sub": str(uuid4()), "org_id": str(uuid4()), "role": "member"}


def _pricing_row(provider="openai", model="gpt-4o"):
    return {
        "id": 1,
        "provider": provider,
        "model": model,
        "input_cost_per_1k_tokens": Decimal("0.0025000000"),
        "output_cost_per_1k_tokens": Decimal("0.0100000000"),
        "valid_from": datetime.now(UTC),
        "valid_to": None,
    }


@pytest.mark.asyncio
async def test_pricing_requires_admin():
    with pytest.raises(HTTPException) as exc_info:
        await list_pricing(user=_member())

    assert exc_info.value.status_code == 403


@pytest.mark.asyncio
async def test_list_pricing_uses_filters(fake_db):
    result = await list_pricing(
        provider="OpenAI",
        model="gpt",
        include_expired=False,
        user=_admin(),
    )

    assert result[0]["provider"] == "openai"
    assert fake_db.params[-1]["provider"] == "openai"
    assert fake_db.params[-1]["model"] == "gpt"
    assert fake_db.params[-1]["model_like"] == "%gpt%"
    assert fake_db.params[-1]["include_expired"] is False


@pytest.mark.asyncio
async def test_create_pricing_closes_previous_record_and_invalidates_cache(
    fake_db, fake_redis
):
    valid_from = datetime.now(UTC)

    result = await create_pricing(
        PricingCreate(
            provider="OpenAI",
            model="gpt-4o",
            input_cost_per_1k_tokens=Decimal("0.0025"),
            output_cost_per_1k_tokens=Decimal("0.0100"),
            valid_from=valid_from,
        ),
        user=_admin(),
    )

    assert result["provider"] == "openai"
    assert fake_db.params[0] == {
        "provider": "openai",
        "model": "gpt-4o",
        "valid_from": valid_from,
    }
    assert fake_redis.deleted == ["pricing:openai:gpt-4o"]


@pytest.mark.asyncio
async def test_update_pricing_rejects_empty_payload():
    with pytest.raises(HTTPException) as exc_info:
        await update_pricing(1, PricingUpdate(), user=_admin())

    assert exc_info.value.status_code == 400


@pytest.mark.asyncio
async def test_update_pricing_changes_valid_from_and_invalidates_cache(
    fake_db, fake_redis
):
    valid_from = datetime.now(UTC)

    result = await update_pricing(
        1,
        PricingUpdate(valid_from=valid_from),
        user=_admin(),
    )

    assert result["valid_from"] == valid_from
    assert fake_db.params[-1]["valid_from"] == valid_from
    assert fake_db.committed is True
    assert fake_redis.deleted == ["pricing:openai:gpt-4o"]


@pytest.mark.asyncio
async def test_end_pricing_sets_valid_to_and_invalidates_cache(fake_db, fake_redis):
    valid_to = datetime.now(UTC)

    result = await end_pricing(
        1,
        PricingEndDate(valid_to=valid_to),
        user=_admin(),
    )

    assert result["valid_to"] == valid_to
    assert fake_db.committed is True
    assert fake_redis.deleted == ["pricing:openai:gpt-4o"]
