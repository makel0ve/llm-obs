import gzip
import json
from contextlib import asynccontextmanager
from uuid import uuid4

import pytest

from app.services.ingest import BatchStatusService
from app.services.storage import (
    PayloadStorageResult,
    StorageService,
    parse_redact_keys,
    redact_payload,
    should_store_payload,
)
from app.workers import process_span as process_span_module
from app.workers.process_span import process_span_batch, sanitize_span_metadata


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


class FakeResult:
    def __init__(self, row=None):
        self.row = row

    def mappings(self):
        return self

    def one_or_none(self):
        return self.row


class FakeDb:
    def __init__(self, payload_settings: dict):
        self.payload_settings = payload_settings

    async def execute(self, *args, **kwargs):
        return FakeResult(self.payload_settings)

    async def commit(self):
        return None


async def _noop_kiq(*args, **kwargs):
    return None


async def _bulk_insert_spans(spans: list[dict], db):
    return [(span["id"], span["started_at"]) for span in spans]


@pytest.fixture(autouse=True, scope="session")
def patch_app_engine():
    yield


@pytest.fixture(autouse=True)
def patch_outbox_delivery_enqueue(monkeypatch):
    monkeypatch.setattr(
        process_span_module.deliver_span_outbox_events, "kiq", _noop_kiq
    )


def make_span_payload() -> dict:
    trace_id = str(uuid4())
    span_id = str(uuid4())
    return {
        "trace_id": trace_id,
        "span_id": span_id,
        "name": "llm.completion",
        "provider": "openai",
        "model": "gpt-4o",
        "input_tokens": 10,
        "output_tokens": 5,
        "latency_ms": 250,
        "started_at": "2026-07-09T10:00:00Z",
        "input_messages": [{"role": "user", "content": "hello"}],
        "output": "world",
        "metadata": {},
    }


def test_redact_payload_replaces_nested_sensitive_keys():
    redact_keys = parse_redact_keys("api_key,Authorization,password")
    payload = {
        "messages": [
            {
                "role": "user",
                "content": "hello",
                "api_key": "secret-key",
                "nested": {"Authorization": "Bearer secret", "safe": "visible"},
            }
        ],
        "output": {"password": "secret-password"},
    }

    redacted = redact_payload(payload, redact_keys)

    assert redacted["messages"][0]["api_key"] == "[redacted]"
    assert redacted["messages"][0]["nested"]["Authorization"] == "[redacted]"
    assert redacted["messages"][0]["nested"]["safe"] == "visible"
    assert redacted["output"]["password"] == "[redacted]"


def test_sanitize_span_metadata_redacts_nested_values_and_drops_payload_like_keys():
    metadata = {
        "source": "anthropic",
        "system": "private system prompt",
        "nested": {
            "Authorization": "Bearer secret-token",
            "safe": "visible",
        },
    }

    sanitized = sanitize_span_metadata(
        metadata, parse_redact_keys("authorization,api_key")
    )

    assert "system" not in sanitized
    assert sanitized["nested"]["Authorization"] == "[redacted]"
    assert sanitized["nested"]["safe"] == "visible"
    assert "private system prompt" not in json.dumps(sanitized)
    assert "secret-token" not in json.dumps(sanitized)


@pytest.mark.parametrize(
    ("mode", "has_error", "expected"),
    [
        ("all", False, True),
        ("all", True, True),
        ("errors", False, False),
        ("errors", True, True),
        ("none", True, False),
    ],
)
def test_should_store_payload(mode: str, has_error: bool, expected: bool):
    assert should_store_payload(mode, has_error=has_error) is expected


@pytest.mark.asyncio
async def test_store_payload_reports_oversized_without_s3_write():
    result = await StorageService().store_payload(
        project_id=str(uuid4()),
        span_id=str(uuid4()),
        messages=[{"role": "user", "content": "private prompt"}],
        output="private output",
        max_bytes=1,
        redact_keys={"content"},
    )

    assert result == PayloadStorageResult(
        s3_key=None, status="too_large", drop_reason="max_bytes_exceeded"
    )


@pytest.mark.asyncio
async def test_store_payload_writes_small_payload_to_s3(monkeypatch):
    stored_objects = []

    class FakeS3Client:
        async def __aenter__(self):
            return self

        async def __aexit__(self, exc_type, exc, tb):
            return None

        async def put_object(self, **kwargs):
            stored_objects.append(kwargs)

    class FakeSession:
        def client(self, *args, **kwargs):
            return FakeS3Client()

    monkeypatch.setattr("app.services.storage.aioboto3.Session", lambda: FakeSession())
    project_id = str(uuid4())
    span_id = str(uuid4())

    result = await StorageService().store_payload(
        project_id=project_id,
        span_id=span_id,
        messages=[{"role": "user", "content": "small private prompt"}],
        output="small private output",
        max_bytes=262144,
        redact_keys={"authorization"},
    )

    assert result.s3_key == f"payloads/{project_id}/{span_id[:2]}/{span_id}.json.gz"
    assert result.status == "stored_redacted"
    assert result.drop_reason is None
    assert len(stored_objects) == 1
    assert stored_objects[0]["Key"] == result.s3_key
    body = gzip.decompress(stored_objects[0]["Body"]).decode()
    assert "small private prompt" in body
    assert "small private output" in body


@pytest.mark.asyncio
async def test_worker_applies_error_only_payload_policy(monkeypatch):
    project_id = str(uuid4())
    batch_id = str(uuid4())
    ok_span = make_span_payload()
    error_span = make_span_payload() | {
        "error": "failed",
        "input_messages": [{"role": "user", "content": "hello", "api_key": "secret"}],
    }
    fake_redis = FakeRedis()
    await BatchStatusService(redis=fake_redis).create_accepted(
        project_id=project_id, batch_id=batch_id, accepted=2
    )
    stored_payloads = []

    @asynccontextmanager
    async def fake_get_db(project_id=None):
        yield FakeDb(
            {
                "payload_storage_mode": "errors",
                "payload_max_bytes": 262144,
                "payload_redact_keys": "api_key",
            }
        )

    async def fake_cost(self, **kwargs):
        return "0.00000000"

    async def fake_store_payload(self, **kwargs):
        stored_payloads.append(kwargs)
        return PayloadStorageResult(s3_key="payload-key", status="stored_redacted")

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

    await process_span_batch.original_func(
        batch_id=batch_id, project_id=project_id, spans=[ok_span, error_span]
    )

    assert len(stored_payloads) == 1
    assert stored_payloads[0]["span_id"] == error_span["span_id"]
    payload_json = json.dumps(
        {
            "messages": redact_payload(
                stored_payloads[0]["messages"], stored_payloads[0]["redact_keys"]
            ),
            "output": stored_payloads[0]["output"],
        }
    )
    assert "secret" not in payload_json
    assert stored_payloads[0]["max_bytes"] == 262144


@pytest.mark.asyncio
async def test_worker_records_payload_drop_reason_for_error_only_policy(monkeypatch):
    project_id = str(uuid4())
    batch_id = str(uuid4())
    ok_span = make_span_payload()
    fake_redis = FakeRedis()
    inserted_spans = []
    await BatchStatusService(redis=fake_redis).create_accepted(
        project_id=project_id, batch_id=batch_id, accepted=1
    )

    @asynccontextmanager
    async def fake_get_db(project_id=None):
        yield FakeDb(
            {
                "payload_storage_mode": "errors",
                "payload_max_bytes": 262144,
                "payload_redact_keys": "api_key",
            }
        )

    async def fake_cost(self, **kwargs):
        return "0.00000000"

    async def fake_store_payload(self, **kwargs):
        raise AssertionError("non-error span should not reach payload storage")

    async def fake_bulk_insert_spans(spans: list[dict], db):
        inserted_spans.extend(spans)
        return [(span["id"], span["started_at"]) for span in spans]

    async def fake_get_redis():
        return fake_redis

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

    await process_span_batch.original_func(
        batch_id=batch_id, project_id=project_id, spans=[ok_span]
    )

    assert inserted_spans[0]["payload_s3_key"] is None
    assert inserted_spans[0]["payload_status"] == "omitted"
    assert inserted_spans[0]["payload_drop_reason"] == "errors_only_non_error"


@pytest.mark.asyncio
async def test_worker_storage_mode_none_keeps_anthropic_payload_out_of_db_s3_and_status(
    monkeypatch,
):
    project_id = str(uuid4())
    batch_id = str(uuid4())
    private_system_prompt = "private anthropic system prompt"
    private_user_input = "private user input"
    private_output = "private model output"
    nested_secret = "nested metadata token"
    span = make_span_payload() | {
        "provider": "anthropic",
        "model": "claude-3-5-sonnet",
        "input_messages": [{"role": "user", "content": private_user_input}],
        "output": private_output,
        "metadata": {
            "system": private_system_prompt,
            "nested": {"authorization": nested_secret, "safe": "visible"},
        },
    }
    fake_redis = FakeRedis()
    inserted_spans = []
    await BatchStatusService(redis=fake_redis).create_accepted(
        project_id=project_id, batch_id=batch_id, accepted=1
    )

    @asynccontextmanager
    async def fake_get_db(project_id=None):
        yield FakeDb(
            {
                "payload_storage_mode": "none",
                "payload_max_bytes": 262144,
                "payload_redact_keys": "authorization,api_key",
            }
        )

    async def fake_cost(self, **kwargs):
        return "0.00000000"

    async def fake_store_payload(self, **kwargs):
        raise AssertionError("payload_storage_mode=none must not write to S3")

    async def fake_bulk_insert_spans(spans: list[dict], db):
        inserted_spans.extend(spans)
        return [(span["id"], span["started_at"]) for span in spans]

    async def fake_get_redis():
        return fake_redis

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

    await process_span_batch.original_func(
        batch_id=batch_id, project_id=project_id, spans=[span]
    )

    assert len(inserted_spans) == 1
    inserted = inserted_spans[0]
    assert inserted["payload_s3_key"] is None
    assert inserted["payload_status"] == "omitted"
    assert inserted["payload_drop_reason"] == "storage_mode_none"
    assert json.loads(inserted["metadata"]) == {
        "nested": {"authorization": "[redacted]", "safe": "visible"}
    }

    db_fields_json = json.dumps(inserted, default=str)
    status_json = json.dumps(fake_redis.values, default=str)
    for raw_value in (
        private_system_prompt,
        private_user_input,
        private_output,
        nested_secret,
    ):
        assert raw_value not in db_fields_json
        assert raw_value not in status_json


@pytest.mark.asyncio
async def test_worker_records_small_payload_object_key_when_storage_is_enabled(
    monkeypatch,
):
    project_id = str(uuid4())
    batch_id = str(uuid4())
    span = make_span_payload() | {
        "input_messages": [{"role": "user", "content": "small prompt"}],
        "output": "small output",
    }
    fake_redis = FakeRedis()
    inserted_spans = []
    await BatchStatusService(redis=fake_redis).create_accepted(
        project_id=project_id, batch_id=batch_id, accepted=1
    )

    @asynccontextmanager
    async def fake_get_db(project_id=None):
        yield FakeDb(
            {
                "payload_storage_mode": "all",
                "payload_max_bytes": 262144,
                "payload_redact_keys": "authorization,api_key",
            }
        )

    async def fake_cost(self, **kwargs):
        return "0.00000000"

    async def fake_store_payload(self, **kwargs):
        return PayloadStorageResult(s3_key="payload-key", status="stored_redacted")

    async def fake_bulk_insert_spans(spans: list[dict], db):
        inserted_spans.extend(spans)
        return [(span["id"], span["started_at"]) for span in spans]

    async def fake_get_redis():
        return fake_redis

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

    await process_span_batch.original_func(
        batch_id=batch_id, project_id=project_id, spans=[span]
    )

    assert inserted_spans[0]["payload_s3_key"] == "payload-key"
    assert inserted_spans[0]["payload_status"] == "stored_redacted"
    assert inserted_spans[0]["payload_drop_reason"] is None


@pytest.mark.asyncio
async def test_store_payload_redacts_nested_payload_before_s3_write(monkeypatch):
    stored_objects = []

    class FakeS3Client:
        async def __aenter__(self):
            return self

        async def __aexit__(self, exc_type, exc, tb):
            return None

        async def put_object(self, **kwargs):
            stored_objects.append(kwargs)

    class FakeSession:
        def client(self, *args, **kwargs):
            return FakeS3Client()

    monkeypatch.setattr("app.services.storage.aioboto3.Session", lambda: FakeSession())

    result = await StorageService().store_payload(
        project_id=str(uuid4()),
        span_id=str(uuid4()),
        messages=[
            {
                "role": "user",
                "content": "x" * 5000,
                "nested": {"authorization": "Bearer secret"},
            }
        ],
        output="private output",
        max_bytes=262144,
        redact_keys={"authorization"},
    )

    assert result.status == "stored_redacted"
    assert len(stored_objects) == 1
    body = gzip.decompress(stored_objects[0]["Body"]).decode()
    assert "Bearer secret" not in body
    assert '"authorization": "[redacted]"' in body
