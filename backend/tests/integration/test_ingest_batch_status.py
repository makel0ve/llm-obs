from contextlib import asynccontextmanager
from uuid import uuid4

import pytest
from fastapi import HTTPException, Response

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

    async def publish(self, channel: str, message: str):
        self.published.append((channel, message))
        return 1


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
    async def execute(self, *args, **kwargs):
        return FakeResult(
            {
                "payload_storage_mode": "all",
                "payload_max_bytes": 262144,
                "payload_redact_keys": "api_key,password,secret,token,authorization",
            }
        )

    async def commit(self):
        return None


def _project(project_id: str) -> dict:
    return {"id": project_id, "org_id": str(uuid4()), "name": "Test Project"}


def _counter_value(counter, *labels: str) -> float:
    return counter.labels(*labels)._value.get()


def _simple_counter_value(counter) -> float:
    return counter._value.get()


async def _noop_kiq(*args, **kwargs):
    return None


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

    async def fake_bulk_insert_spans(spans: list[dict], db) -> int:
        inserted_spans.extend(spans)
        return len(spans)

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


async def _bulk_insert_spans(spans: list[dict], db) -> int:
    return len(spans)
