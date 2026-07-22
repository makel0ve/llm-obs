from collections.abc import Callable, Iterator
from datetime import UTC, datetime

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

    def labels(self, *, queue: str) -> FakeGaugeChild:
        child = FakeGaugeChild()
        self.children[queue] = child
        return child


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

    assert list(depth_gauge.children) == ["taskiq"]
    assert list(age_gauge.children) == ["taskiq"]
    depth_callback = depth_gauge.children["taskiq"].callback
    age_callback = age_gauge.children["taskiq"].callback
    assert depth_callback is not None
    assert age_callback is not None
    assert depth_callback() == 7.0
    assert age_callback() == 9.0
