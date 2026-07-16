from decimal import Decimal
from uuid import uuid4

import pytest

from app.workers.process_span import evaluate_windowed_alert_rule


@pytest.fixture(autouse=True, scope="session")
def patch_app_engine() -> None:
    return None


class FakeResult:
    def __init__(self, row: dict[str, object]) -> None:
        self._row = row

    def mappings(self) -> "FakeResult":
        return self

    def one(self) -> dict[str, object]:
        return self._row


class FakeDb:
    def __init__(self, row: dict[str, object]) -> None:
        self.row = row
        self.statements: list[str] = []
        self.params: list[dict[str, object]] = []

    async def execute(self, statement: object, params: dict[str, object]) -> FakeResult:
        self.statements.append(str(statement))
        self.params.append(params)
        return FakeResult(self.row)


def _rule(
    *,
    metric: str,
    condition: str = "gt",
    threshold: Decimal | None = Decimal("10"),
    window_minutes: int = 15,
) -> dict[str, object]:
    return {
        "id": str(uuid4()),
        "name": f"{metric} rule",
        "metric": metric,
        "condition": condition,
        "threshold": threshold,
        "window_minutes": window_minutes,
    }


@pytest.mark.asyncio
async def test_latency_p95_rule_uses_windowed_percentile() -> None:
    db = FakeDb({"value": 750.0, "sample_count": 20})

    triggered, value = await evaluate_windowed_alert_rule(
        db=db,
        project_id="project-1",
        rule=_rule(metric="latency_p95", threshold=Decimal("500"), window_minutes=7),
    )

    assert triggered is True
    assert value == 750.0
    assert "percentile_cont(0.95)" in db.statements[0]
    assert db.params[0] == {"project_id": "project-1", "window_minutes": 7}


@pytest.mark.asyncio
async def test_error_rate_rule_uses_windowed_error_percentage() -> None:
    db = FakeDb({"value": Decimal("12.5"), "sample_count": 40})

    triggered, value = await evaluate_windowed_alert_rule(
        db=db,
        project_id="project-1",
        rule=_rule(metric="error_rate", threshold=Decimal("10")),
    )

    assert triggered is True
    assert value == 12.5
    assert "COUNT(*) FILTER (WHERE status = 'error')" in db.statements[0]


@pytest.mark.asyncio
async def test_cost_hourly_rule_uses_windowed_cost_sum() -> None:
    db = FakeDb({"value": Decimal("25.50"), "sample_count": 12})

    triggered, value = await evaluate_windowed_alert_rule(
        db=db,
        project_id="project-1",
        rule=_rule(metric="cost_hourly", threshold=Decimal("20"), window_minutes=60),
    )

    assert triggered is True
    assert value == 25.5
    assert "SUM(cost_usd)" in db.statements[0]
    assert db.params[0]["window_minutes"] == 60


@pytest.mark.asyncio
async def test_windowed_rule_does_not_trigger_without_samples() -> None:
    db = FakeDb({"value": Decimal("999"), "sample_count": 0})

    triggered, value = await evaluate_windowed_alert_rule(
        db=db,
        project_id="project-1",
        rule=_rule(metric="latency_p95", threshold=Decimal("1")),
    )

    assert triggered is False
    assert value == 999.0


@pytest.mark.asyncio
async def test_windowed_rule_supports_less_than_condition() -> None:
    db = FakeDb({"value": Decimal("2"), "sample_count": 5})

    triggered, value = await evaluate_windowed_alert_rule(
        db=db,
        project_id="project-1",
        rule=_rule(metric="error_rate", condition="lt", threshold=Decimal("5")),
    )

    assert triggered is True
    assert value == 2.0
