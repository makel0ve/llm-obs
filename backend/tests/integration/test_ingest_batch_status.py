import asyncio
from contextlib import asynccontextmanager
from uuid import uuid4

import pytest
from fastapi import HTTPException, Response
from sqlalchemy.exc import SQLAlchemyError

from app.api.v1.ingest import get_ingest_batch_status, ingest_spans
from app.core.metrics import (
    ingest_batches_accepted,
    ingest_batches_failed,
    ingest_batches_processed,
    ingest_spans_dropped,
    spans_ingested,
)
from app.schemas.ingest import IngestRequest
from app.services.ingest import BatchStatusService, IngestService
from app.services.storage import PayloadStorageResult
from app.workers import process_span as process_span_module
from app.workers.process_span import process_span_batch
from tests.factories import make_span_payload


class FakeRedis:
    def __init__(self):
        self.values = {}
        self.published = []

    async def get(self, key: str):
        return self.values.get(key)

    async def setex(self, key: str, ttl: int, value: str):
        self.values[key] = value
        return True

    async def set(
        self, key: str, value: str, *, ex: int | None = None, nx: bool = False
    ):
        if nx and key in self.values:
            return None

        self.values[key] = value
        return True

    async def delete(self, key: str):
        self.values.pop(key, None)
        return 1

    async def publish(self, channel: str, message: str):
        self.published.append((channel, message))
        return 1


class FailingPublishRedis(FakeRedis):
    async def publish(self, channel: str, message: str):
        raise RuntimeError("redis publish unavailable")


class FakeRateLimiter:
    async def check(self, project_id: str, response):
        response.headers["X-RateLimit-Limit"] = "1000"


class FakeResult:
    def __init__(self, row=None):
        self.row = row

    def mappings(self):
        return self

    def one_or_none(self):
        return self.row


class FakeDb:
    def __init__(self):
        self.commit_count = 0

    async def execute(self, *args, **kwargs):
        return FakeResult(
            {
                "payload_storage_mode": "all",
                "payload_max_bytes": 262144,
                "payload_redact_keys": "api_key,password,secret,token,authorization",
            }
        )

    async def commit(self):
        self.commit_count += 1
        return None


def _project(project_id: str) -> dict:
    return {"id": project_id, "org_id": str(uuid4()), "name": "Test Project"}


def _counter_value(counter, *labels: str) -> float:
    return counter.labels(*labels)._value.get()


def _simple_counter_value(counter) -> float:
    return counter._value.get()


async def _noop_kiq(*args, **kwargs):
    return None


def _patch_worker_common(monkeypatch, redis, db):
    @asynccontextmanager
    async def fake_get_db(project_id=None):
        yield db

    async def fake_cost(self, **kwargs):
        return "0.00000000"

    async def fake_store_payload(self, **kwargs):
        return PayloadStorageResult(
            s3_key=None, status="omitted", drop_reason="below_inline_threshold"
        )

    async def fake_get_redis():
        return redis

    monkeypatch.setattr(process_span_module, "get_redis", fake_get_redis)
    monkeypatch.setattr(process_span_module, "get_db", fake_get_db)
    monkeypatch.setattr(process_span_module.CostService, "calculate", fake_cost)
    monkeypatch.setattr(
        process_span_module.StorageService, "store_payload", fake_store_payload
    )


class FailingKiq:
    def __init__(self, error: str):
        self.error = error
        self.called = False

    async def kiq(self, **kwargs):
        self.called = True
        raise RuntimeError(self.error)


@pytest.fixture(autouse=True, scope="session")
def patch_app_engine():
    yield


@pytest.fixture
def fake_redis():
    return FakeRedis()


@pytest.mark.asyncio
async def test_ingest_creates_accepted_batch_status(monkeypatch, fake_redis):
    project_id = str(uuid4())
    service = IngestService(redis=fake_redis)
    enqueued = {}

    class FakeProcessSpanBatch:
        async def kiq(self, **kwargs):
            enqueued.update(kwargs)

    monkeypatch.setattr(
        process_span_module, "process_span_batch", FakeProcessSpanBatch()
    )

    accepted_before = _simple_counter_value(ingest_batches_accepted)
    response = await ingest_spans(
        payload=IngestRequest(spans=[make_span_payload()]),
        response=Response(),
        project=_project(project_id),
        service=service,
        rate_limiter=FakeRateLimiter(),
    )

    batch_id = response.batch_id
    assert enqueued["batch_id"] == batch_id
    assert enqueued["project_id"] == project_id

    batch_status = await get_ingest_batch_status(
        batch_id=batch_id, project=_project(project_id), service=service
    )

    status_payload = batch_status.model_dump(mode="json")
    assert (
        status_payload
        | {
            "batch_id": batch_id,
            "status": "accepted",
            "accepted": 1,
            "processed": 0,
            "failed": 0,
            "error": None,
        }
        == status_payload
    )
    assert _simple_counter_value(ingest_batches_accepted) == accepted_before + 1


@pytest.mark.asyncio
async def test_ingest_reuses_atomic_idempotency_reservation(monkeypatch, fake_redis):
    project_id = str(uuid4())
    service = IngestService(redis=fake_redis)
    enqueued = []
    payload = IngestRequest(spans=[make_span_payload()], idempotency_key="idem-key")

    class FakeProcessSpanBatch:
        async def kiq(self, **kwargs):
            enqueued.append(kwargs)

    monkeypatch.setattr(
        process_span_module, "process_span_batch", FakeProcessSpanBatch()
    )

    first = await ingest_spans(
        payload=payload,
        response=Response(),
        project=_project(project_id),
        service=service,
        rate_limiter=FakeRateLimiter(),
    )
    second = await ingest_spans(
        payload=payload,
        response=Response(),
        project=_project(project_id),
        service=service,
        rate_limiter=FakeRateLimiter(),
    )

    assert second == first
    assert len(enqueued) == 1
    assert enqueued[0]["batch_id"] == first.batch_id


@pytest.mark.asyncio
async def test_ingest_rejects_idempotency_key_for_different_body(
    monkeypatch, fake_redis
):
    project_id = str(uuid4())
    service = IngestService(redis=fake_redis)
    enqueued = []

    class FakeProcessSpanBatch:
        async def kiq(self, **kwargs):
            enqueued.append(kwargs)

    monkeypatch.setattr(
        process_span_module, "process_span_batch", FakeProcessSpanBatch()
    )

    await ingest_spans(
        payload=IngestRequest(spans=[make_span_payload()], idempotency_key="idem-key"),
        response=Response(),
        project=_project(project_id),
        service=service,
        rate_limiter=FakeRateLimiter(),
    )

    changed_span = make_span_payload()
    changed_span["metadata"] = {"changed": True}
    with pytest.raises(HTTPException) as exc_info:
        await ingest_spans(
            payload=IngestRequest(spans=[changed_span], idempotency_key="idem-key"),
            response=Response(),
            project=_project(project_id),
            service=service,
            rate_limiter=FakeRateLimiter(),
        )

    assert exc_info.value.status_code == 409
    assert len(enqueued) == 1


@pytest.mark.asyncio
async def test_concurrent_identical_idempotency_requests_enqueue_once(
    monkeypatch, fake_redis
):
    project_id = str(uuid4())
    service = IngestService(redis=fake_redis)
    enqueued = []
    payload = IngestRequest(spans=[make_span_payload()], idempotency_key="idem-key")

    class FakeProcessSpanBatch:
        async def kiq(self, **kwargs):
            await asyncio.sleep(0)
            enqueued.append(kwargs)

    monkeypatch.setattr(
        process_span_module, "process_span_batch", FakeProcessSpanBatch()
    )

    first, second = await asyncio.gather(
        ingest_spans(
            payload=payload,
            response=Response(),
            project=_project(project_id),
            service=service,
            rate_limiter=FakeRateLimiter(),
        ),
        ingest_spans(
            payload=payload,
            response=Response(),
            project=_project(project_id),
            service=service,
            rate_limiter=FakeRateLimiter(),
        ),
    )

    assert second == first
    assert len(enqueued) == 1
    assert enqueued[0]["batch_id"] == first.batch_id


@pytest.mark.asyncio
async def test_batch_status_is_project_scoped(fake_redis):
    project_a = str(uuid4())
    project_b = str(uuid4())
    batch_id = str(uuid4())
    service = IngestService(redis=fake_redis)
    await BatchStatusService(redis=fake_redis).create_accepted(
        project_id=project_a, batch_id=batch_id, accepted=1
    )

    with pytest.raises(HTTPException) as exc_info:
        await get_ingest_batch_status(
            batch_id=batch_id, project=_project(project_b), service=service
        )

    assert exc_info.value.status_code == 404


@pytest.mark.asyncio
async def test_ingest_marks_batch_failed_when_enqueue_fails(monkeypatch, fake_redis):
    project_id = str(uuid4())
    service = IngestService(redis=fake_redis)

    class FailingProcessSpanBatch:
        async def kiq(self, **kwargs):
            raise RuntimeError("queue unavailable")

    monkeypatch.setattr(
        process_span_module, "process_span_batch", FailingProcessSpanBatch()
    )

    failed_before = _counter_value(ingest_batches_failed, "enqueue")
    with pytest.raises(RuntimeError):
        await ingest_spans(
            payload=IngestRequest(spans=[make_span_payload()]),
            response=Response(),
            project=_project(project_id),
            service=service,
            rate_limiter=FakeRateLimiter(),
        )

    [batch_id] = [
        key.rsplit(":", 1)[-1]
        for key in fake_redis.values
        if key.startswith(f"ingest_batch:{project_id}:")
    ]
    status = await BatchStatusService(redis=fake_redis).get(
        project_id=project_id, batch_id=batch_id
    )
    assert status is not None
    assert status.status == "failed"
    assert status.error == "queue unavailable"
    assert _counter_value(ingest_batches_failed, "enqueue") == failed_before + 1


@pytest.mark.asyncio
async def test_worker_marks_batch_processed(monkeypatch, fake_redis):
    project_id = str(uuid4())
    batch_id = str(uuid4())
    span = make_span_payload()
    span["parent_span_id"] = str(uuid4())
    inserted_spans = []
    await BatchStatusService(redis=fake_redis).create_accepted(
        project_id=project_id, batch_id=batch_id, accepted=1
    )

    @asynccontextmanager
    async def fake_get_db(project_id=None):
        yield FakeDb()

    async def fake_cost(self, **kwargs):
        return "0.00000000"

    async def fake_store_payload(self, **kwargs):
        return PayloadStorageResult(
            s3_key=None, status="omitted", drop_reason="below_inline_threshold"
        )

    async def fake_get_redis():
        return fake_redis

    async def fake_bulk_insert_spans(spans: list[dict], db):
        inserted_spans.extend(spans)
        return [(span["id"], span["started_at"]) for span in spans]

    monkeypatch.setattr(process_span_module, "get_redis", fake_get_redis)
    monkeypatch.setattr(process_span_module, "get_db", fake_get_db)
    monkeypatch.setattr(process_span_module.CostService, "calculate", fake_cost)
    monkeypatch.setattr(
        process_span_module.StorageService, "store_payload", fake_store_payload
    )
    monkeypatch.setattr(
        process_span_module, "bulk_insert_spans", fake_bulk_insert_spans
    )
    monkeypatch.setattr(process_span_module.update_trace_aggregates, "kiq", _noop_kiq)
    monkeypatch.setattr(process_span_module.check_batch_anomalies, "kiq", _noop_kiq)

    processed_before = _counter_value(ingest_batches_processed, "processed")
    span_before = _counter_value(spans_ingested, "openai", "gpt-4o", "ok")
    await process_span_batch.original_func(
        batch_id=batch_id, project_id=project_id, spans=[span]
    )

    status = await BatchStatusService(redis=fake_redis).get(
        project_id=project_id, batch_id=batch_id
    )
    assert status is not None
    assert status.status == "processed"
    assert status.processed == 1
    assert status.failed == 0
    assert _counter_value(ingest_batches_processed, "processed") == (
        processed_before + 1
    )
    assert _counter_value(spans_ingested, "openai", "gpt-4o", "ok") == (span_before + 1)
    assert str(inserted_spans[0]["parent_span_id"]) == span["parent_span_id"]
    assert inserted_spans[0]["payload_status"] == "omitted"
    assert inserted_spans[0]["payload_drop_reason"] == "below_inline_threshold"


@pytest.mark.asyncio
async def test_worker_counts_only_inserted_spans_when_duplicates_are_ignored(
    monkeypatch, fake_redis
):
    project_id = str(uuid4())
    batch_id = str(uuid4())
    inserted_span = make_span_payload()
    duplicate_span = make_span_payload()
    await BatchStatusService(redis=fake_redis).create_accepted(
        project_id=project_id, batch_id=batch_id, accepted=2
    )

    @asynccontextmanager
    async def fake_get_db(project_id=None):
        yield FakeDb()

    async def fake_cost(self, **kwargs):
        return "0.00000000"

    async def fake_store_payload(self, **kwargs):
        return PayloadStorageResult(
            s3_key=None, status="omitted", drop_reason="below_inline_threshold"
        )

    async def fake_get_redis():
        return fake_redis

    async def fake_bulk_insert_spans(spans: list[dict], db):
        return [(spans[0]["id"], spans[0]["started_at"])]

    monkeypatch.setattr(process_span_module, "get_redis", fake_get_redis)
    monkeypatch.setattr(process_span_module, "get_db", fake_get_db)
    monkeypatch.setattr(process_span_module.CostService, "calculate", fake_cost)
    monkeypatch.setattr(
        process_span_module.StorageService, "store_payload", fake_store_payload
    )
    monkeypatch.setattr(
        process_span_module, "bulk_insert_spans", fake_bulk_insert_spans
    )
    monkeypatch.setattr(process_span_module.update_trace_aggregates, "kiq", _noop_kiq)
    monkeypatch.setattr(process_span_module.check_batch_anomalies, "kiq", _noop_kiq)

    span_before = _counter_value(spans_ingested, "openai", "gpt-4o", "ok")
    await process_span_batch.original_func(
        batch_id=batch_id, project_id=project_id, spans=[inserted_span, duplicate_span]
    )

    status = await BatchStatusService(redis=fake_redis).get(
        project_id=project_id, batch_id=batch_id
    )
    assert status is not None
    assert status.status == "processed"
    assert status.accepted == 2
    assert status.processed == 1
    assert status.failed == 0
    assert _counter_value(spans_ingested, "openai", "gpt-4o", "ok") == (span_before + 1)
    assert len(fake_redis.published) == 1


@pytest.mark.asyncio
async def test_worker_marks_batch_partial_failed(monkeypatch, fake_redis):
    project_id = str(uuid4())
    batch_id = str(uuid4())
    valid_span = make_span_payload()
    invalid_span = make_span_payload() | {"started_at": "not-a-date"}
    await BatchStatusService(redis=fake_redis).create_accepted(
        project_id=project_id, batch_id=batch_id, accepted=2
    )

    @asynccontextmanager
    async def fake_get_db(project_id=None):
        yield FakeDb()

    async def fake_cost(self, **kwargs):
        return "0.00000000"

    async def fake_store_payload(self, **kwargs):
        return PayloadStorageResult(
            s3_key=None, status="storage_failed", drop_reason="s3_error"
        )

    async def fake_get_redis():
        return fake_redis

    monkeypatch.setattr(process_span_module, "get_redis", fake_get_redis)
    monkeypatch.setattr(process_span_module, "get_db", fake_get_db)
    monkeypatch.setattr(process_span_module.CostService, "calculate", fake_cost)
    monkeypatch.setattr(
        process_span_module.StorageService, "store_payload", fake_store_payload
    )
    monkeypatch.setattr(process_span_module, "bulk_insert_spans", _bulk_insert_spans)
    monkeypatch.setattr(process_span_module.update_trace_aggregates, "kiq", _noop_kiq)
    monkeypatch.setattr(process_span_module.check_batch_anomalies, "kiq", _noop_kiq)

    processed_before = _counter_value(ingest_batches_processed, "partial_failed")
    dropped_before = _counter_value(ingest_spans_dropped, "processing_error")
    await process_span_batch.original_func(
        batch_id=batch_id, project_id=project_id, spans=[valid_span, invalid_span]
    )

    status = await BatchStatusService(redis=fake_redis).get(
        project_id=project_id, batch_id=batch_id
    )
    assert status is not None
    assert status.status == "partial_failed"
    assert status.processed == 1
    assert status.failed == 1
    assert _counter_value(ingest_batches_processed, "partial_failed") == (
        processed_before + 1
    )
    assert _counter_value(ingest_spans_dropped, "processing_error") == (
        dropped_before + 1
    )


@pytest.mark.asyncio
async def test_worker_failure_after_span_insert_rolls_back_spans_and_trace(
    monkeypatch, fake_redis
):
    project_id = str(uuid4())
    batch_id = str(uuid4())
    span = make_span_payload()
    db = FakeDb()
    attempted_spans = []
    aggregate_task_calls = []
    anomaly_task_calls = []
    await BatchStatusService(redis=fake_redis).create_accepted(
        project_id=project_id, batch_id=batch_id, accepted=1
    )
    _patch_worker_common(monkeypatch, fake_redis, db)

    async def fake_bulk_insert_spans(spans: list[dict], db):
        attempted_spans.extend(spans)
        return [(span["id"], span["started_at"]) for span in spans]

    async def fail_trace_row(**kwargs):
        raise RuntimeError("trace insert failed before db commit")

    async def capture_aggregate(**kwargs):
        aggregate_task_calls.append(kwargs)

    async def capture_anomaly(**kwargs):
        anomaly_task_calls.append(kwargs)

    monkeypatch.setattr(
        process_span_module, "bulk_insert_spans", fake_bulk_insert_spans
    )
    monkeypatch.setattr(process_span_module, "ensure_trace_row", fail_trace_row)
    monkeypatch.setattr(
        process_span_module.update_trace_aggregates, "kiq", capture_aggregate
    )
    monkeypatch.setattr(
        process_span_module.check_batch_anomalies, "kiq", capture_anomaly
    )

    failed_before = _counter_value(ingest_batches_failed, "worker")
    with pytest.raises(RuntimeError, match="trace insert failed"):
        await process_span_batch.original_func(
            batch_id=batch_id, project_id=project_id, spans=[span]
        )

    status = await BatchStatusService(redis=fake_redis).get(
        project_id=project_id, batch_id=batch_id
    )
    assert status is not None
    assert status.status == "failed"
    assert status.error == "trace insert failed before db commit"
    assert len(attempted_spans) == 1
    assert db.commit_count == 0
    assert fake_redis.published == []
    assert aggregate_task_calls == []
    assert anomaly_task_calls == []
    assert _counter_value(ingest_batches_failed, "worker") == failed_before + 1


@pytest.mark.asyncio
async def test_worker_failure_during_pubsub_keeps_db_committed_but_marks_failed(
    monkeypatch,
):
    project_id = str(uuid4())
    batch_id = str(uuid4())
    span = make_span_payload()
    redis = FailingPublishRedis()
    db = FakeDb()
    committed_spans = []
    trace_rows = []
    await BatchStatusService(redis=redis).create_accepted(
        project_id=project_id, batch_id=batch_id, accepted=1
    )
    _patch_worker_common(monkeypatch, redis, db)

    async def fake_bulk_insert_spans(spans: list[dict], db):
        committed_spans.extend(spans)
        return [(span["id"], span["started_at"]) for span in spans]

    async def fake_ensure_trace_row(**kwargs):
        trace_rows.append(kwargs)
        return kwargs["started_at"]

    monkeypatch.setattr(
        process_span_module, "bulk_insert_spans", fake_bulk_insert_spans
    )
    monkeypatch.setattr(process_span_module, "ensure_trace_row", fake_ensure_trace_row)
    monkeypatch.setattr(process_span_module.update_trace_aggregates, "kiq", _noop_kiq)
    monkeypatch.setattr(process_span_module.check_batch_anomalies, "kiq", _noop_kiq)

    with pytest.raises(RuntimeError, match="redis publish unavailable"):
        await process_span_batch.original_func(
            batch_id=batch_id, project_id=project_id, spans=[span]
        )

    status = await BatchStatusService(redis=redis).get(
        project_id=project_id, batch_id=batch_id
    )
    assert status is not None
    assert status.status == "failed"
    assert status.error == "redis publish unavailable"
    assert len(committed_spans) == 1
    assert len(trace_rows) == 1
    assert db.commit_count == 1


@pytest.mark.asyncio
async def test_worker_failure_during_aggregate_enqueue_keeps_db_committed(
    monkeypatch, fake_redis
):
    project_id = str(uuid4())
    batch_id = str(uuid4())
    span = make_span_payload()
    db = FakeDb()
    committed_spans = []
    trace_rows = []
    failing_aggregate = FailingKiq("aggregate enqueue unavailable")
    await BatchStatusService(redis=fake_redis).create_accepted(
        project_id=project_id, batch_id=batch_id, accepted=1
    )
    _patch_worker_common(monkeypatch, fake_redis, db)

    async def fake_bulk_insert_spans(spans: list[dict], db):
        committed_spans.extend(spans)
        return [(span["id"], span["started_at"]) for span in spans]

    async def fake_ensure_trace_row(**kwargs):
        trace_rows.append(kwargs)
        return kwargs["started_at"]

    monkeypatch.setattr(
        process_span_module, "bulk_insert_spans", fake_bulk_insert_spans
    )
    monkeypatch.setattr(process_span_module, "ensure_trace_row", fake_ensure_trace_row)
    monkeypatch.setattr(
        process_span_module.update_trace_aggregates, "kiq", failing_aggregate.kiq
    )
    monkeypatch.setattr(process_span_module.check_batch_anomalies, "kiq", _noop_kiq)

    with pytest.raises(RuntimeError, match="aggregate enqueue unavailable"):
        await process_span_batch.original_func(
            batch_id=batch_id, project_id=project_id, spans=[span]
        )

    status = await BatchStatusService(redis=fake_redis).get(
        project_id=project_id, batch_id=batch_id
    )
    assert status is not None
    assert status.status == "failed"
    assert status.error == "aggregate enqueue unavailable"
    assert len(committed_spans) == 1
    assert len(trace_rows) == 1
    assert len(fake_redis.published) == 1
    assert db.commit_count == 1
    assert failing_aggregate.called is True


@pytest.mark.asyncio
async def test_worker_transient_cost_error_is_retryable_worker_failure(
    monkeypatch, fake_redis
):
    project_id = str(uuid4())
    batch_id = str(uuid4())
    span = make_span_payload()
    db = FakeDb()
    inserted_spans = []
    await BatchStatusService(redis=fake_redis).create_accepted(
        project_id=project_id, batch_id=batch_id, accepted=1
    )
    _patch_worker_common(monkeypatch, fake_redis, db)

    async def failing_cost(self, **kwargs):
        raise SQLAlchemyError("pricing database unavailable")

    async def fake_bulk_insert_spans(spans: list[dict], db):
        inserted_spans.extend(spans)
        return []

    monkeypatch.setattr(process_span_module.CostService, "calculate", failing_cost)
    monkeypatch.setattr(
        process_span_module, "bulk_insert_spans", fake_bulk_insert_spans
    )
    monkeypatch.setattr(process_span_module.update_trace_aggregates, "kiq", _noop_kiq)
    monkeypatch.setattr(process_span_module.check_batch_anomalies, "kiq", _noop_kiq)

    failed_before = _counter_value(ingest_batches_failed, "worker")
    dropped_before = _counter_value(ingest_spans_dropped, "processing_error")
    with pytest.raises(SQLAlchemyError, match="pricing database unavailable"):
        await process_span_batch.original_func(
            batch_id=batch_id, project_id=project_id, spans=[span]
        )

    status = await BatchStatusService(redis=fake_redis).get(
        project_id=project_id, batch_id=batch_id
    )
    assert status is not None
    assert status.status == "failed"
    assert status.processed == 0
    assert status.failed == 0
    assert status.error == "pricing database unavailable"
    assert inserted_spans == []
    assert _counter_value(ingest_batches_failed, "worker") == failed_before + 1
    assert _counter_value(ingest_spans_dropped, "processing_error") == dropped_before


async def _bulk_insert_spans(spans: list[dict], db):
    return [(span["id"], span["started_at"]) for span in spans]
