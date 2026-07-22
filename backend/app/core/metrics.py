import asyncio
import importlib
import json
from collections.abc import Callable, Coroutine
from datetime import UTC, datetime
from queue import Empty, Queue
from threading import Thread
from typing import Any, Protocol, cast

from fastapi import FastAPI
from prometheus_client import Counter, Gauge, Histogram
from prometheus_fastapi_instrumentator import Instrumentator
from redis import Redis
from sqlalchemy.engine import make_url

from app.core.config import settings

TASKIQ_QUEUE_NAME = "taskiq"
OUTBOX_EVENT_TYPE_SPAN_INSERTED = "span.inserted"
OUTBOX_BACKLOG_STATUSES = ("PENDING", "FAILED")
_TASKIQ_QUEUE_TIMESTAMP_KEYS = (
    "enqueued_at",
    "queued_at",
    "created_at",
    "sent_at",
    "timestamp",
)
_taskiq_queue_callbacks_registered = False
_outbox_backlog_callbacks_registered = False
_ASYNC_METRIC_QUERY_TIMEOUT_SECONDS = 2.0


class QueueRedis(Protocol):
    def llen(self, key: str) -> int: ...

    def lindex(self, key: str, index: int) -> str | None: ...

    def close(self) -> None: ...


ingest_batches_accepted = Counter(
    "llmobs_ingest_batches_accepted_total",
    "Ingest batches accepted for asynchronous processing",
)
ingest_batches_processed = Counter(
    "llmobs_ingest_batches_processed_total",
    "Ingest batches processed by worker",
    ["status"],
)
ingest_batches_failed = Counter(
    "llmobs_ingest_batches_failed_total",
    "Ingest batches failed before or during worker processing",
    ["stage"],
)
ingest_batch_processing_s = Histogram(
    "llmobs_ingest_batch_processing_seconds",
    "Wall-clock seconds spent processing an ingest batch",
    buckets=[0.01, 0.05, 0.1, 0.5, 1.0, 5.0, 30.0],
)
ingest_batch_accepted_to_processing_s = Histogram(
    "llmobs_ingest_batch_accepted_to_processing_seconds",
    "Seconds between ingest API acceptance and worker processing start",
    buckets=[0.01, 0.05, 0.1, 0.5, 1.0, 5.0, 30.0, 120.0, 600.0],
)
ingest_batch_accepted_to_finished_s = Histogram(
    "llmobs_ingest_batch_accepted_to_finished_seconds",
    "Seconds between ingest API acceptance and final worker batch status",
    buckets=[0.01, 0.05, 0.1, 0.5, 1.0, 5.0, 30.0, 120.0, 600.0],
)
ingest_span_source_to_accepted_s = Histogram(
    "llmobs_ingest_span_source_to_accepted_seconds",
    "Seconds between span timestamp and ingest API batch acceptance",
    buckets=[0.0, 0.1, 1.0, 5.0, 30.0, 120.0, 600.0, 3600.0],
)
ingest_span_source_to_processed_s = Histogram(
    "llmobs_ingest_span_source_to_processed_seconds",
    "Seconds between span timestamp and worker processing completion",
    buckets=[0.0, 0.1, 1.0, 5.0, 30.0, 120.0, 600.0, 3600.0],
)
ingest_spans_dropped = Counter(
    "llmobs_ingest_spans_dropped_total",
    "Spans dropped during ingest batch processing",
    ["reason"],
)
ingest_span_processing_failures = Counter(
    "llmobs_ingest_span_processing_failures_total",
    "Individual spans dropped before persistence by bounded processing failure reason",
    ["reason"],
)
spans_ingested = Counter(
    "llmobs_spans_ingested_total", "LLM spans ingested", ["provider", "model", "status"]
)
span_processing_s = Histogram(
    "llmobs_span_processing_seconds",
    "Span batch processing time",
    buckets=[0.01, 0.05, 0.1, 0.5, 1.0, 5.0],
)
failed_tasks = Counter(
    "llmobs_failed_tasks_total", "Permanently failed tasks", ["task_name"]
)
payload_storage_failures = Counter(
    "llmobs_payload_storage_failures_total",
    "Payload object storage failures",
    ["stage"],
)
payload_storage_results = Counter(
    "llmobs_payload_storage_results_total",
    "Payload storage decisions by bounded status and reason",
    ["status", "reason"],
)
outbox_delivery_attempts = Counter(
    "llmobs_outbox_delivery_attempts_total",
    "Outbox delivery attempts by bounded event type and result",
    ["event_type", "result"],
)
taskiq_queue_depth = Gauge(
    "llmobs_taskiq_queue_depth",
    "Pending Taskiq jobs in Redis list queues",
    ["queue"],
)
taskiq_queue_oldest_job_age_s = Gauge(
    "llmobs_taskiq_queue_oldest_job_age_seconds",
    "Best-effort age in seconds of the oldest pending Taskiq job",
    ["queue"],
)
outbox_backlog = Gauge(
    "llmobs_outbox_backlog",
    "Outbox events waiting for delivery by bounded event type and status",
    ["event_type", "status"],
)


def _get_queue_redis() -> QueueRedis:
    return cast(
        QueueRedis,
        Redis.from_url(
            settings.effective_redis_queue_url,
            decode_responses=True,
            socket_connect_timeout=0.5,
            socket_timeout=0.5,
        ),
    )


def taskiq_queue_depth_value(queue_name: str = TASKIQ_QUEUE_NAME) -> float:
    try:
        redis = _get_queue_redis()
        try:
            return float(redis.llen(queue_name))
        finally:
            redis.close()
    except Exception:
        return 0.0


def taskiq_queue_oldest_job_age_value(
    queue_name: str = TASKIQ_QUEUE_NAME,
    *,
    now: datetime | None = None,
) -> float:
    observed_at = now or datetime.now(UTC)
    try:
        redis = _get_queue_redis()
        try:
            if redis.llen(queue_name) <= 0:
                return 0.0
            raw_job = redis.lindex(queue_name, -1)
        finally:
            redis.close()
    except Exception:
        return 0.0

    return estimate_taskiq_queued_job_age_seconds(raw_job, now=observed_at)


def estimate_taskiq_queued_job_age_seconds(
    raw_job: str | bytes | None,
    *,
    now: datetime | None = None,
) -> float:
    queued_at = parse_taskiq_queued_job_timestamp(raw_job)
    if queued_at is None:
        return 0.0

    observed_at = now or datetime.now(UTC)
    if observed_at.tzinfo is None:
        observed_at = observed_at.replace(tzinfo=UTC)
    else:
        observed_at = observed_at.astimezone(UTC)

    return max((observed_at - queued_at).total_seconds(), 0.0)


def parse_taskiq_queued_job_timestamp(raw_job: str | bytes | None) -> datetime | None:
    if raw_job is None:
        return None

    if isinstance(raw_job, bytes):
        try:
            raw_job = raw_job.decode()
        except UnicodeDecodeError:
            return None

    try:
        payload = json.loads(raw_job)
    except json.JSONDecodeError:
        return None

    return _find_taskiq_timestamp(payload)


def _find_taskiq_timestamp(value: object) -> datetime | None:
    if isinstance(value, dict):
        for key in _TASKIQ_QUEUE_TIMESTAMP_KEYS:
            timestamp = _parse_timestamp_value(value.get(key))
            if timestamp is not None:
                return timestamp

        for child in value.values():
            timestamp = _find_taskiq_timestamp(child)
            if timestamp is not None:
                return timestamp

    if isinstance(value, list):
        for child in value:
            timestamp = _find_taskiq_timestamp(child)
            if timestamp is not None:
                return timestamp

    return None


def _parse_timestamp_value(value: Any) -> datetime | None:
    if isinstance(value, str):
        try:
            parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
        except ValueError:
            return None
    elif isinstance(value, int | float):
        try:
            parsed = datetime.fromtimestamp(float(value), tz=UTC)
        except (OverflowError, OSError, ValueError):
            return None
    else:
        return None

    if parsed.tzinfo is None:
        return parsed.replace(tzinfo=UTC)

    return parsed.astimezone(UTC)


def register_taskiq_queue_metric_callbacks(
    queue_name: str = TASKIQ_QUEUE_NAME,
) -> None:
    global _taskiq_queue_callbacks_registered

    if _taskiq_queue_callbacks_registered:
        return

    _set_gauge_callback(
        taskiq_queue_depth.labels(queue=queue_name),
        lambda: taskiq_queue_depth_value(queue_name),
    )
    _set_gauge_callback(
        taskiq_queue_oldest_job_age_s.labels(queue=queue_name),
        lambda: taskiq_queue_oldest_job_age_value(queue_name),
    )
    _taskiq_queue_callbacks_registered = True


async def query_outbox_backlog_count(event_type: str, status: str) -> float:
    connection = await _connect_outbox_metrics_db()
    try:
        result = await connection.fetchval(
            """
            SELECT COUNT(*)
            FROM outbox_events
            WHERE event_type = $1
                AND status = $2
            """,
            event_type,
            status,
        )
    finally:
        await connection.close()

    return float(result or 0)


def _asyncpg_database_url() -> str:
    url = make_url(settings.database_url.get_secret_value())
    return str(url.set(drivername="postgresql"))


async def _connect_outbox_metrics_db() -> Any:
    asyncpg = importlib.import_module("asyncpg")
    return await asyncpg.connect(
        dsn=_asyncpg_database_url(),
        timeout=_ASYNC_METRIC_QUERY_TIMEOUT_SECONDS,
        command_timeout=_ASYNC_METRIC_QUERY_TIMEOUT_SECONDS,
        statement_cache_size=0,
    )


def outbox_backlog_value(event_type: str, status: str) -> float:
    return _run_async_metric_query(
        lambda: query_outbox_backlog_count(event_type=event_type, status=status)
    )


def register_outbox_backlog_metric_callbacks(
    event_type: str = OUTBOX_EVENT_TYPE_SPAN_INSERTED,
) -> None:
    global _outbox_backlog_callbacks_registered

    if _outbox_backlog_callbacks_registered:
        return

    for status in OUTBOX_BACKLOG_STATUSES:
        _set_gauge_callback(
            outbox_backlog.labels(event_type=event_type, status=status),
            _make_outbox_backlog_callback(event_type=event_type, status=status),
        )

    _outbox_backlog_callbacks_registered = True


def _make_outbox_backlog_callback(event_type: str, status: str) -> Callable[[], float]:
    return lambda: outbox_backlog_value(event_type, status)


def _run_async_metric_query(
    coro_factory: Callable[[], Coroutine[Any, Any, float]],
) -> float:
    results: Queue[float] = Queue(maxsize=1)

    def run_query() -> None:
        try:
            value = float(asyncio.run(coro_factory()))
        except Exception:
            value = 0.0

        try:
            results.put_nowait(value)
        except Exception:
            return

    Thread(target=run_query, name="llmobs-metric-query", daemon=True).start()

    try:
        return results.get(timeout=_ASYNC_METRIC_QUERY_TIMEOUT_SECONDS)
    except Empty:
        return 0.0


def _set_gauge_callback(gauge: Any, callback: Callable[[], float]) -> None:
    gauge.set_function(callback)


def setup_metrics(app: FastAPI) -> None:
    register_taskiq_queue_metric_callbacks()
    register_outbox_backlog_metric_callbacks()
    Instrumentator().instrument(app).expose(app)
