import asyncio
import json
from contextlib import asynccontextmanager
from datetime import UTC, datetime
from decimal import Decimal
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
from app.services import cost as cost_module
from app.services.ingest import (
    BatchStatusService,
    IdempotencyConflictError,
    IdempotencyInProgressError,
    IngestService,
)
from app.services.outbox import OUTBOX_SPAN_INSERTED, OutboxEventPayload
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


class MemoryIdempotencyStore:
    def __init__(self):
        self.records = {}
        self.lock = asyncio.Lock()

    async def reserve(self, project_id: str, key: str, request_hash: str, result: dict):
        record_key = (project_id, key)
        async with self.lock:
            existing = self.records.get(record_key)
            if existing is None:
                self.records[record_key] = {
                    "request_hash": request_hash,
                    "status": "PENDING",
                    "result": result,
                }
                return None

            if existing["request_hash"] != request_hash:
                raise IdempotencyConflictError

            if existing["status"] == "COMMITTED":
                return existing["result"]

            if existing["status"] == "FAILED":
                existing.update(status="PENDING", result=result)
                return None

            raise IdempotencyInProgressError

    async def commit(
        self, project_id: str, key: str, request_hash: str, result: dict
    ) -> None:
        self.records[(project_id, key)].update(status="COMMITTED", result=result)

    async def fail(self, project_id: str, key: str, request_hash: str) -> None:
        self.records[(project_id, key)].update(status="FAILED", result=None)


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


class FakePricingResult:
    def __init__(self, row=None):
        self.row = row

    def mappings(self):
        return self

    def one_or_none(self):
        return self.row


class FakePricingDb:
    def __init__(self):
        self.params = []

    async def execute(self, statement, params=None):
        params = params or {}
        self.params.append(params)
        at_time = params["t"]
        if at_time < datetime(2026, 7, 1, tzinfo=UTC):
            return FakePricingResult(
                {
                    "inp": Decimal("0.001"),
                    "out": Decimal("0.002"),
                    "valid_from": datetime(2026, 1, 1, tzinfo=UTC),
                    "valid_to": datetime(2026, 7, 1, tzinfo=UTC),
                }
            )

        return FakePricingResult(
            {
                "inp": Decimal("0.010"),
                "out": Decimal("0.020"),
                "valid_from": datetime(2026, 7, 1, tzinfo=UTC),
                "valid_to": None,
            }
        )


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
        return PayloadStorageResult(s3_key="payload-key", status="stored_redacted")

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


@pytest.fixture(autouse=True)
def patch_outbox_delivery_enqueue(monkeypatch):
    monkeypatch.setattr(
        process_span_module.deliver_span_outbox_events, "kiq", _noop_kiq
    )


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
    idempotency_store = MemoryIdempotencyStore()
    service = IngestService(redis=fake_redis, idempotency_store=idempotency_store)
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
    assert idempotency_store.records[(project_id, "idem-key")]["status"] == "COMMITTED"


@pytest.mark.asyncio
async def test_ingest_rejects_idempotency_key_for_different_body(
    monkeypatch, fake_redis
):
    project_id = str(uuid4())
    service = IngestService(
        redis=fake_redis, idempotency_store=MemoryIdempotencyStore()
    )
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
    service = IngestService(
        redis=fake_redis, idempotency_store=MemoryIdempotencyStore()
    )
    enqueued = []
    payload = IngestRequest(spans=[make_span_payload()], idempotency_key="idem-key")

    class FakeProcessSpanBatch:
        async def kiq(self, **kwargs):
            await asyncio.sleep(0)
            enqueued.append(kwargs)

    monkeypatch.setattr(
        process_span_module, "process_span_batch", FakeProcessSpanBatch()
    )

    results = await asyncio.gather(
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
        return_exceptions=True,
    )

    successes = [result for result in results if not isinstance(result, Exception)]
    errors = [result for result in results if isinstance(result, HTTPException)]
    assert len(successes) == 1
    assert len(errors) == 1
    assert errors[0].status_code == 409
    assert errors[0].detail == "Idempotency key is already being processed"
    assert len(enqueued) == 1
    assert enqueued[0]["batch_id"] == successes[0].batch_id


@pytest.mark.asyncio
async def test_idempotency_failed_enqueue_can_be_retried(monkeypatch, fake_redis):
    project_id = str(uuid4())
    idempotency_store = MemoryIdempotencyStore()
    service = IngestService(redis=fake_redis, idempotency_store=idempotency_store)
    payload = IngestRequest(spans=[make_span_payload()], idempotency_key="idem-key")
    attempts = 0

    class FlakyProcessSpanBatch:
        async def kiq(self, **kwargs):
            nonlocal attempts
            attempts += 1
            if attempts == 1:
                raise RuntimeError("queue unavailable")

    monkeypatch.setattr(
        process_span_module, "process_span_batch", FlakyProcessSpanBatch()
    )

    with pytest.raises(RuntimeError):
        await ingest_spans(
            payload=payload,
            response=Response(),
            project=_project(project_id),
            service=service,
            rate_limiter=FakeRateLimiter(),
        )

    assert idempotency_store.records[(project_id, "idem-key")]["status"] == "FAILED"

    retry = await ingest_spans(
        payload=payload,
        response=Response(),
        project=_project(project_id),
        service=service,
        rate_limiter=FakeRateLimiter(),
    )

    assert retry.accepted == 1
    assert attempts == 2
    assert idempotency_store.records[(project_id, "idem-key")]["status"] == "COMMITTED"


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
        return PayloadStorageResult(s3_key="payload-key", status="stored_redacted")

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
    assert inserted_spans[0]["payload_s3_key"] == "payload-key"
    assert inserted_spans[0]["payload_status"] == "stored_redacted"
    assert inserted_spans[0]["payload_drop_reason"] is None


@pytest.mark.asyncio
async def test_worker_reuses_pricing_lookup_for_spans_in_same_interval(
    monkeypatch, fake_redis
):
    project_id = str(uuid4())
    batch_id = str(uuid4())
    pricing_db = FakePricingDb()
    inserted_spans = []
    old_span = make_span_payload() | {
        "started_at": datetime(2026, 6, 1, tzinfo=UTC).isoformat(),
        "input_tokens": 1000,
        "output_tokens": 1000,
    }
    same_interval_span = make_span_payload() | {
        "started_at": datetime(2026, 6, 15, tzinfo=UTC).isoformat(),
        "input_tokens": 500,
        "output_tokens": 500,
    }
    new_interval_span = make_span_payload() | {
        "started_at": datetime(2026, 8, 1, tzinfo=UTC).isoformat(),
        "input_tokens": 1000,
        "output_tokens": 1000,
    }
    await BatchStatusService(redis=fake_redis).create_accepted(
        project_id=project_id, batch_id=batch_id, accepted=3
    )

    @asynccontextmanager
    async def fake_worker_get_db(project_id=None):
        yield FakeDb()

    @asynccontextmanager
    async def fake_pricing_get_db():
        yield pricing_db

    async def fake_get_redis():
        return fake_redis

    async def fake_store_payload(self, **kwargs):
        return PayloadStorageResult(
            s3_key=None, status="omitted", drop_reason="below_inline_threshold"
        )

    async def fake_bulk_insert_spans(spans: list[dict], db):
        inserted_spans.extend(spans)
        return [(span["id"], span["started_at"]) for span in spans]

    async def fake_enqueue_outbox_event(**kwargs):
        return None

    monkeypatch.setattr(process_span_module, "get_redis", fake_get_redis)
    monkeypatch.setattr(process_span_module, "get_db", fake_worker_get_db)
    monkeypatch.setattr(cost_module, "get_redis", fake_get_redis)
    monkeypatch.setattr(cost_module, "get_db", fake_pricing_get_db)
    monkeypatch.setattr(
        process_span_module.StorageService, "store_payload", fake_store_payload
    )
    monkeypatch.setattr(
        process_span_module, "bulk_insert_spans", fake_bulk_insert_spans
    )
    monkeypatch.setattr(
        process_span_module, "enqueue_outbox_event", fake_enqueue_outbox_event
    )
    monkeypatch.setattr(process_span_module.update_trace_aggregates, "kiq", _noop_kiq)
    monkeypatch.setattr(process_span_module.check_batch_anomalies, "kiq", _noop_kiq)

    await process_span_batch.original_func(
        batch_id=batch_id,
        project_id=project_id,
        spans=[old_span, same_interval_span, new_interval_span],
    )

    assert len(pricing_db.params) == 2
    assert [span["cost_usd"] for span in inserted_spans] == [
        Decimal("0.00300000"),
        Decimal("0.00150000"),
        Decimal("0.03000000"),
    ]


@pytest.mark.asyncio
async def test_worker_counts_only_inserted_spans_when_duplicates_are_ignored(
    monkeypatch, fake_redis
):
    project_id = str(uuid4())
    batch_id = str(uuid4())
    inserted_span = make_span_payload()
    duplicate_span = make_span_payload()
    outbox_events = []
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

    async def fake_enqueue_outbox_event(**kwargs):
        outbox_events.append(kwargs)

    monkeypatch.setattr(process_span_module, "get_redis", fake_get_redis)
    monkeypatch.setattr(process_span_module, "get_db", fake_get_db)
    monkeypatch.setattr(process_span_module.CostService, "calculate", fake_cost)
    monkeypatch.setattr(
        process_span_module.StorageService, "store_payload", fake_store_payload
    )
    monkeypatch.setattr(
        process_span_module, "bulk_insert_spans", fake_bulk_insert_spans
    )
    monkeypatch.setattr(
        process_span_module, "enqueue_outbox_event", fake_enqueue_outbox_event
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
    assert fake_redis.published == []
    assert len(outbox_events) == 1
    assert outbox_events[0]["event_type"] == OUTBOX_SPAN_INSERTED
    assert outbox_events[0]["event_key"] == str(inserted_span["span_id"])


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
async def test_worker_writes_pubsub_outbox_before_commit_and_processes_batch(
    monkeypatch,
):
    project_id = str(uuid4())
    batch_id = str(uuid4())
    span = make_span_payload()
    redis = FailingPublishRedis()
    db = FakeDb()
    committed_spans = []
    trace_rows = []
    outbox_events = []
    bucket_updates = []
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

    async def fake_enqueue_outbox_event(**kwargs):
        assert db.commit_count == 0
        outbox_events.append(kwargs)

    async def fake_update_span_metric_buckets(**kwargs):
        assert db.commit_count == 0
        bucket_updates.append(kwargs)

    monkeypatch.setattr(
        process_span_module, "bulk_insert_spans", fake_bulk_insert_spans
    )
    monkeypatch.setattr(process_span_module, "ensure_trace_row", fake_ensure_trace_row)
    monkeypatch.setattr(
        process_span_module, "enqueue_outbox_event", fake_enqueue_outbox_event
    )
    monkeypatch.setattr(
        process_span_module,
        "update_span_metric_buckets",
        fake_update_span_metric_buckets,
    )
    monkeypatch.setattr(process_span_module.update_trace_aggregates, "kiq", _noop_kiq)
    monkeypatch.setattr(process_span_module.check_batch_anomalies, "kiq", _noop_kiq)

    await process_span_batch.original_func(
        batch_id=batch_id, project_id=project_id, spans=[span]
    )

    status = await BatchStatusService(redis=redis).get(
        project_id=project_id, batch_id=batch_id
    )
    assert status is not None
    assert status.status == "processed"
    assert status.error is None
    assert len(committed_spans) == 1
    assert len(trace_rows) == 1
    assert db.commit_count == 1
    assert redis.published == []
    assert len(outbox_events) == 1
    assert outbox_events[0]["event_type"] == OUTBOX_SPAN_INSERTED
    assert outbox_events[0]["event_key"] == span["span_id"]
    assert outbox_events[0]["payload"] == {
        "span_id": span["span_id"],
        "name": span["name"],
        "latency_ms": span["latency_ms"],
        "status": "ok",
    }
    assert bucket_updates == [
        {"db": db, "project_id": project_id, "spans": committed_spans}
    ]


@pytest.mark.asyncio
async def test_span_outbox_delivery_marks_failed_then_retry_delivered(monkeypatch):
    project_id = uuid4()
    event_id = uuid4()
    event = OutboxEventPayload(
        id=event_id,
        project_id=project_id,
        event_type=OUTBOX_SPAN_INSERTED,
        event_key=str(uuid4()),
        payload={
            "span_id": str(uuid4()),
            "name": "llm_call",
            "latency_ms": 42,
            "status": "ok",
        },
        attempts=1,
    )
    redis = FailingPublishRedis()
    failed = []
    delivered = []

    class FakeOutboxService:
        async def claim_pending(self, **kwargs):
            return [event]

        async def mark_failed(self, event_id, error):
            failed.append((event_id, error))

        async def mark_delivered(self, event_id):
            delivered.append(event_id)

    async def fake_get_redis():
        return redis

    monkeypatch.setattr(process_span_module, "OutboxService", FakeOutboxService)
    monkeypatch.setattr(process_span_module, "get_redis", fake_get_redis)

    with pytest.raises(RuntimeError, match="redis publish unavailable"):
        await process_span_module.deliver_span_outbox_events.original_func(
            project_id=project_id
        )

    assert failed == [(event_id, "redis publish unavailable")]
    assert delivered == []

    redis = FakeRedis()
    await process_span_module.deliver_span_outbox_events.original_func(
        project_id=str(project_id)
    )

    assert len(redis.published) == 1
    channel, message = redis.published[0]
    assert channel == f"project:{project_id}:new_span"
    assert json.loads(message) == event.payload
    assert delivered == [event_id]


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
    outbox_events = []
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

    async def fake_enqueue_outbox_event(**kwargs):
        outbox_events.append(kwargs)

    monkeypatch.setattr(
        process_span_module, "bulk_insert_spans", fake_bulk_insert_spans
    )
    monkeypatch.setattr(process_span_module, "ensure_trace_row", fake_ensure_trace_row)
    monkeypatch.setattr(
        process_span_module, "enqueue_outbox_event", fake_enqueue_outbox_event
    )
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
    assert fake_redis.published == []
    assert len(outbox_events) == 1
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
