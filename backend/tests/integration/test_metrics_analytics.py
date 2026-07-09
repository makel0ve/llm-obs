from contextlib import asynccontextmanager
from datetime import UTC, datetime
from decimal import Decimal

import pytest

from app.services import metrics_service
from app.services.metrics_service import MetricsService


@pytest.fixture(autouse=True, scope="session")
def patch_app_engine():
    yield


class FakeResult:
    def __init__(self, rows):
        self._rows = rows

    def mappings(self):
        return self

    def all(self):
        return self._rows


class FakeDb:
    def __init__(self):
        self.statements = []
        self.params = []

    async def execute(self, statement, params):
        sql = str(statement)
        self.statements.append(sql)
        self.params.append(params)

        if "GROUP BY COALESCE(model" in sql and "SUM(cost_usd)" in sql:
            return FakeResult(
                [
                    {
                        "model": "gpt-4o",
                        "total_cost_usd": Decimal("0.01500000"),
                        "total_tokens": 900,
                        "span_count": 3,
                    }
                ]
            )

        if "GROUP BY COALESCE(provider" in sql and "SUM(cost_usd)" in sql:
            return FakeResult(
                [
                    {
                        "provider": "openai",
                        "total_cost_usd": Decimal("0.01500000"),
                        "total_tokens": 900,
                        "span_count": 3,
                    }
                ]
            )

        if "WITH time_buckets" in sql and "error_rate_pct" in sql:
            return FakeResult(
                [
                    {
                        "bucket": datetime(2026, 7, 8, 10, tzinfo=UTC),
                        "span_count": 10,
                        "error_count": 2,
                        "error_rate_pct": Decimal("20.00"),
                    }
                ]
            )

        if "date_trunc(:granularity, started_at)" in sql:
            return FakeResult(
                [
                    {
                        "bucket": datetime(2026, 7, 8, 10, tzinfo=UTC),
                        "total_cost_usd": Decimal("0.01500000"),
                        "span_count": 3,
                    }
                ]
            )

        if "GROUP BY COALESCE(model" in sql and "AVG(latency_ms)" in sql:
            return FakeResult(
                [
                    {
                        "model": "gpt-4o",
                        "avg_latency_ms": Decimal("350.00"),
                        "p95_latency_ms": 500.0,
                        "span_count": 3,
                    }
                ]
            )

        if "GROUP BY COALESCE(provider" in sql and "AVG(latency_ms)" in sql:
            return FakeResult(
                [
                    {
                        "provider": "openai",
                        "avg_latency_ms": Decimal("350.00"),
                        "p95_latency_ms": 500.0,
                        "span_count": 3,
                    }
                ]
            )

        if "GROUP BY LEFT" in sql:
            return FakeResult(
                [
                    {
                        "error_message": "demo error",
                        "error_count": 2,
                        "last_seen_at": datetime(2026, 7, 8, 10, tzinfo=UTC),
                    }
                ]
            )

        if "GROUP BY COALESCE(model" in sql and "error_rate_pct" in sql:
            return FakeResult(
                [
                    {
                        "model": "gpt-4o",
                        "span_count": 10,
                        "error_count": 2,
                        "error_rate_pct": Decimal("20.00"),
                    }
                ]
            )

        if "GROUP BY COALESCE(provider" in sql and "error_rate_pct" in sql:
            return FakeResult(
                [
                    {
                        "provider": "openai",
                        "span_count": 10,
                        "error_count": 2,
                        "error_rate_pct": Decimal("20.00"),
                    }
                ]
            )

        if "ARRAY_AGG" in sql:
            return FakeResult(
                [
                    {
                        "trace_id": "trace-failed",
                        "started_at": datetime(2026, 7, 8, 10, tzinfo=UTC),
                        "error_count": 2,
                        "error_message": "demo error",
                    }
                ]
            )

        if "ORDER BY total_cost_usd DESC" in sql:
            return FakeResult(
                [
                    {
                        "trace_id": "trace-expensive",
                        "total_cost_usd": Decimal("0.01500000"),
                        "span_count": 3,
                        "started_at": datetime(2026, 7, 8, 10, tzinfo=UTC),
                    }
                ]
            )

        if "ORDER BY max_latency_ms DESC" in sql:
            return FakeResult(
                [
                    {
                        "trace_id": "trace-slow",
                        "max_latency_ms": 700.0,
                        "avg_latency_ms": Decimal("500.00"),
                        "span_count": 2,
                        "started_at": datetime(2026, 7, 8, 10, tzinfo=UTC),
                    }
                ]
            )

        raise AssertionError(f"unexpected query: {sql}")


@pytest.mark.asyncio
async def test_get_analytics_returns_cost_latency_and_trace_breakdowns(monkeypatch):
    fake_db = FakeDb()

    @asynccontextmanager
    async def fake_get_db(project_id=None):
        assert project_id == "project-1"
        yield fake_db

    monkeypatch.setattr(metrics_service, "get_db", fake_get_db)

    result = await MetricsService().get_analytics("project-1", "24h")

    assert result["cost_by_model"][0]["model"] == "gpt-4o"
    assert result["cost_by_provider"][0]["provider"] == "openai"
    assert result["cost_over_time"][0]["span_count"] == 3
    assert result["latency_by_model"][0]["p95_latency_ms"] == 500.0
    assert result["latency_by_provider"][0]["avg_latency_ms"] == Decimal("350.00")
    assert result["top_expensive_traces"][0]["trace_id"] == "trace-expensive"
    assert result["slowest_traces"][0]["trace_id"] == "trace-slow"
    assert result["error_rate_trend"][0]["error_rate_pct"] == Decimal("20.00")
    assert result["top_error_messages"][0]["error_message"] == "demo error"
    assert result["errors_by_model"][0]["error_count"] == 2
    assert result["errors_by_provider"][0]["provider"] == "openai"
    assert result["recent_failed_traces"][0]["trace_id"] == "trace-failed"
    assert len(fake_db.statements) == 12
    assert all(params["project_id"] == "project-1" for params in fake_db.params)
