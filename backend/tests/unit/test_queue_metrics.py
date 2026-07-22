from collections.abc import Callable, Iterator
from datetime import UTC, datetime
from typing import Any

import pytest

from app.core import metrics


@pytest.fixture(autouse=True, scope="session")
def patch_app_engine() -> Iterator[None]:
    yield


class FakeQueueRedis:
    def __init__(self, messages: list[str]) -> None:
        self.messages = messages
        self.llen_calls: list[str] = []
        self.lindex_calls: list[tuple[str, int]] = []
        self.closed = False

    def llen(self, key: str) -> int:
        self.llen_calls.append(key)
        return len(self.messages)

    def lindex(self, key: str, index: int) -> str | None:
        self.lindex_calls.append((key, index))
        if not self.messages:
            return None

        return self.messages[index]

    def close(self) -> None:
        self.closed = True


class FakeGaugeChild:
    def __init__(self) -> None:
        self.callback: Callable[[], float] | None = None

    def set_function(self, callback: Callable[[], float]) -> None:
        self.callback = callback


class FakeGauge:
    def __init__(self) -> None:
        self.children: dict[str, FakeGaugeChild] = {}

    def labels(self, **labels: str) -> FakeGaugeChild:
        child = FakeGaugeChild()
        key = "|".join(f"{key}={value}" for key, value in sorted(labels.items()))
        self.children[key] = child
        return child


class FakeAsyncpgConnection:
    def __init__(self, value: int) -> None:
        self.value = value
        self.calls: list[tuple[str, str]] = []
        self.closed = False

    async def fetchval(self, query: str, event_type: str, status: str) -> int:
        self.calls.append((event_type, status))
        return self.value

    async def close(self) -> None:
        self.closed = True


class FakeAsyncpg:
    def __init__(self, value: int) -> None:
        self.connection = FakeAsyncpgConnection(value=value)
        self.kwargs: dict[str, Any] | None = None

    async def connect(self, **kwargs: Any) -> FakeAsyncpgConnection:
        self.kwargs = kwargs
        return self.connection


def test_taskiq_queue_depth_value_reads_redis_list_length(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    queue_redis = FakeQueueRedis(["job-a", "job-b"])

    monkeypatch.setattr(metrics, "_get_queue_redis", lambda: queue_redis)

    assert metrics.taskiq_queue_depth_value("taskiq") == 2.0
    assert queue_redis.llen_calls == ["taskiq"]
    assert queue_redis.closed is True


def test_taskiq_queue_oldest_job_age_reads_rightmost_list_item(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    queued_at = datetime(2026, 7, 22, 12, 0, 0, tzinfo=UTC)
    queue_redis = FakeQueueRedis(
        [
            '{"task": "newer", "created_at": "2026-07-22T12:00:30+00:00"}',
            f'{{"task": "older", "created_at": "{queued_at.isoformat()}"}}',
        ]
    )

    monkeypatch.setattr(metrics, "_get_queue_redis", lambda: queue_redis)

    age = metrics.taskiq_queue_oldest_job_age_value(
        "taskiq",
        now=datetime(2026, 7, 22, 12, 1, 0, tzinfo=UTC),
    )

    assert age == 60.0
    assert queue_redis.llen_calls == ["taskiq"]
    assert queue_redis.lindex_calls == [("taskiq", -1)]
    assert queue_redis.closed is True


def test_taskiq_queue_oldest_job_age_reports_zero_for_empty_queue(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    queue_redis = FakeQueueRedis([])

    monkeypatch.setattr(metrics, "_get_queue_redis", lambda: queue_redis)

    assert metrics.taskiq_queue_oldest_job_age_value("taskiq") == 0.0
    assert queue_redis.llen_calls == ["taskiq"]
    assert queue_redis.lindex_calls == []
    assert queue_redis.closed is True


def test_estimate_queued_job_age_returns_zero_for_opaque_payload() -> None:
    age = metrics.estimate_taskiq_queued_job_age_seconds(
        "not-json",
        now=datetime(2026, 7, 22, 12, 1, 0, tzinfo=UTC),
    )

    assert age == 0.0


def test_register_taskiq_queue_metric_callbacks_is_idempotent(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    depth_gauge = FakeGauge()
    age_gauge = FakeGauge()

    monkeypatch.setattr(metrics, "_taskiq_queue_callbacks_registered", False)
    monkeypatch.setattr(metrics, "taskiq_queue_depth", depth_gauge)
    monkeypatch.setattr(metrics, "taskiq_queue_oldest_job_age_s", age_gauge)
    monkeypatch.setattr(metrics, "taskiq_queue_depth_value", lambda queue: 7.0)
    monkeypatch.setattr(metrics, "taskiq_queue_oldest_job_age_value", lambda queue: 9.0)

    metrics.register_taskiq_queue_metric_callbacks("taskiq")
    metrics.register_taskiq_queue_metric_callbacks("taskiq")

    assert list(depth_gauge.children) == ["queue=taskiq"]
    assert list(age_gauge.children) == ["queue=taskiq"]
    depth_callback = depth_gauge.children["queue=taskiq"].callback
    age_callback = age_gauge.children["queue=taskiq"].callback
    assert depth_callback is not None
    assert age_callback is not None
    assert depth_callback() == 7.0
    assert age_callback() == 9.0


@pytest.mark.asyncio
async def test_query_outbox_backlog_count_reads_bounded_status(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    asyncpg = FakeAsyncpg(value=3)

    monkeypatch.setattr(
        metrics, "_connect_outbox_metrics_db", lambda: asyncpg.connect(dsn="db")
    )

    count = await metrics.query_outbox_backlog_count("span.inserted", "FAILED")

    assert count == 3.0
    assert asyncpg.kwargs is not None
    assert asyncpg.kwargs["dsn"] == "db"
    assert asyncpg.connection.calls == [("span.inserted", "FAILED")]
    assert asyncpg.connection.closed is True


def test_outbox_backlog_value_returns_zero_when_query_fails(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    async def fail_query(event_type: str, status: str) -> float:
        raise RuntimeError("postgres unavailable")

    monkeypatch.setattr(metrics, "query_outbox_backlog_count", fail_query)

    assert metrics.outbox_backlog_value("span.inserted", "PENDING") == 0.0


def test_register_outbox_backlog_metric_callbacks_is_idempotent(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    backlog_gauge = FakeGauge()

    monkeypatch.setattr(metrics, "_outbox_backlog_callbacks_registered", False)
    monkeypatch.setattr(metrics, "outbox_backlog", backlog_gauge)
    monkeypatch.setattr(
        metrics,
        "outbox_backlog_value",
        lambda event_type, status: 5.0 if status == "PENDING" else 2.0,
    )

    metrics.register_outbox_backlog_metric_callbacks("span.inserted")
    metrics.register_outbox_backlog_metric_callbacks("span.inserted")

    assert list(backlog_gauge.children) == [
        "event_type=span.inserted|status=PENDING",
        "event_type=span.inserted|status=FAILED",
    ]
    pending_callback = backlog_gauge.children[
        "event_type=span.inserted|status=PENDING"
    ].callback
    failed_callback = backlog_gauge.children[
        "event_type=span.inserted|status=FAILED"
    ].callback
    assert pending_callback is not None
    assert failed_callback is not None
    assert pending_callback() == 5.0
    assert failed_callback() == 2.0
