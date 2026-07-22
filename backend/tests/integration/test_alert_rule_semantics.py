from decimal import Decimal
from uuid import uuid4

import pytest

from app.workers import process_span as process_span_module
from app.workers.process_span import (
    check_batch_anomalies,
    evaluate_scheduled_alert_rules,
    evaluate_windowed_alert_rule,
)


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


class FakeContextDb(FakeDb):
    async def __aenter__(self) -> "FakeContextDb":
        return self

    async def __aexit__(self, *args: object) -> None:
        return None


def _rule(
    *,
    metric: str,
    condition: str = "gt",
    threshold: Decimal | None = Decimal("10"),
    window_minutes: int = 15,
    project_id: str = "project-1",
) -> dict[str, object]:
    return {
        "id": str(uuid4()),
        "project_id": project_id,
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


@pytest.mark.asyncio
async def test_batch_alert_check_ignores_windowed_rules_in_hot_path(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    project_id = "project-1"
    rules = [
        _rule(metric="latency_p95", threshold=Decimal("999")),
        _rule(metric="error_rate", threshold=Decimal("999")),
        _rule(metric="cost_hourly", threshold=Decimal("999")),
    ]
    rules_db = FakeContextDb({"value": 0, "sample_count": 0})
    rules_db.row = {}
    opened_dbs: list[FakeContextDb] = []

    class RulesResult:
        def mappings(self) -> "RulesResult":
            return self

        def all(self) -> list[dict[str, object]]:
            return rules

    async def execute_rules_query(
        statement: object, params: dict[str, object]
    ) -> RulesResult:
        rules_db.statements.append(str(statement))
        rules_db.params.append(params)
        return RulesResult()

    rules_db.execute = execute_rules_query  # type: ignore[assignment,method-assign]

    def fake_get_db(project_id: str | None = None) -> FakeContextDb:
        if project_id is None:
            opened_dbs.append(rules_db)
            return rules_db

        assert project_id == "project-1"
        raise AssertionError("batch hot path must not run windowed alert SQL")

    monkeypatch.setattr(process_span_module, "get_db", fake_get_db)

    await check_batch_anomalies.original_func(project_id=project_id, spans=[])

    assert len(opened_dbs) == 1
    assert "metric = 'anomaly'" in opened_dbs[0].statements[0]


@pytest.mark.asyncio
async def test_scheduled_alert_check_runs_one_aggregation_per_windowed_rule(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    rules = [
        _rule(metric="latency_p95", threshold=Decimal("999"), project_id="project-1"),
        _rule(metric="error_rate", threshold=Decimal("999"), project_id="project-1"),
        _rule(metric="cost_hourly", threshold=Decimal("999"), project_id="project-2"),
    ]
    rules_db = FakeContextDb({"value": 0, "sample_count": 0})
    aggregation_dbs = [
        FakeContextDb({"value": 100.0, "sample_count": 10}),
        FakeContextDb({"value": Decimal("1.5"), "sample_count": 10}),
        FakeContextDb({"value": Decimal("2.50"), "sample_count": 10}),
    ]
    opened_dbs: list[FakeContextDb] = []
    cooldown_checks: list[str] = []

    class RulesResult:
        def mappings(self) -> "RulesResult":
            return self

        def all(self) -> list[dict[str, object]]:
            return rules

    async def execute_rules_query(
        statement: object, params: dict[str, object]
    ) -> RulesResult:
        rules_db.statements.append(str(statement))
        rules_db.params.append(params)
        return RulesResult()

    class FakeNotificationService:
        async def is_on_cooldown(self, rule_id: object) -> bool:
            cooldown_checks.append(str(rule_id))
            return False

        async def send_alert(
            self, rule: dict[str, object], value: float, message: str
        ) -> bool:
            return False

    rules_db.execute = execute_rules_query  # type: ignore[assignment,method-assign]

    def fake_get_db(project_id: str | None = None) -> FakeContextDb:
        if project_id is None:
            opened_dbs.append(rules_db)
            return rules_db

        db = aggregation_dbs.pop(0)
        opened_dbs.append(db)
        return db

    monkeypatch.setattr(process_span_module, "get_db", fake_get_db)
    monkeypatch.setattr(
        process_span_module, "NotificationService", FakeNotificationService
    )

    await evaluate_scheduled_alert_rules.original_func()

    aggregation_statements = [
        statement for db in opened_dbs[1:] for statement in db.statements
    ]
    assert len(aggregation_statements) == 3
    assert "percentile_cont(0.95)" in aggregation_statements[0]
    assert "COUNT(*) FILTER (WHERE status = 'error')" in aggregation_statements[1]
    assert "SUM(cost_usd)" in aggregation_statements[2]
    assert (
        "metric IN ('latency_p95', 'error_rate', 'cost_hourly')"
        in (opened_dbs[0].statements[0])
    )
    assert len(cooldown_checks) == 3
    aggregation_params = [params for db in opened_dbs[1:] for params in db.params]
    assert aggregation_params == [
        {"project_id": "project-1", "window_minutes": 15},
        {"project_id": "project-1", "window_minutes": 15},
        {"project_id": "project-2", "window_minutes": 15},
    ]


@pytest.mark.asyncio
async def test_scheduled_alert_cooldown_precheck_skips_aggregation_sql(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    events: list[str] = []
    rule = _rule(metric="latency_p95", threshold=Decimal("10"))
    rules_db = FakeContextDb({})
    value_db = FakeContextDb({"value": 100.0, "sample_count": 1})

    class RulesResult:
        def mappings(self) -> "RulesResult":
            return self

        def all(self) -> list[dict[str, object]]:
            return [rule]

    async def execute_rules_query(
        statement: object, params: dict[str, object]
    ) -> RulesResult:
        events.append("rules_sql")
        rules_db.statements.append(str(statement))
        rules_db.params.append(params)
        return RulesResult()

    async def execute_value_query(
        statement: object, params: dict[str, object]
    ) -> FakeResult:
        events.append("aggregation_sql")
        value_db.statements.append(str(statement))
        value_db.params.append(params)
        return FakeResult(value_db.row)

    class FakeNotificationService:
        async def is_on_cooldown(self, rule_id: object) -> bool:
            events.append("cooldown_precheck")
            return True

        async def send_alert(
            self, rule: dict[str, object], value: float, message: str
        ) -> bool:
            events.append("send_alert")
            return False

    rules_db.execute = execute_rules_query  # type: ignore[assignment,method-assign]
    value_db.execute = execute_value_query  # type: ignore[method-assign]

    def fake_get_db(project_id: str | None = None) -> FakeContextDb:
        return rules_db if project_id is None else value_db

    monkeypatch.setattr(process_span_module, "get_db", fake_get_db)
    monkeypatch.setattr(
        process_span_module, "NotificationService", FakeNotificationService
    )

    await evaluate_scheduled_alert_rules.original_func()

    assert events == ["rules_sql", "cooldown_precheck"]
    assert value_db.statements == []
