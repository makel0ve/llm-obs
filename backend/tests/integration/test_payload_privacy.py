import json
from contextlib import asynccontextmanager
from uuid import uuid4

import pytest

from app.services.ingest import BatchStatusService
from app.services.storage import parse_redact_keys, redact_payload, should_store_payload
from app.workers import process_span as process_span_module
from app.workers.process_span import process_span_batch


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


async def _bulk_insert_spans(spans: list[dict], db) -> int:
    return len(spans)


@pytest.fixture(autouse=True, scope="session")
def patch_app_engine():
    yield


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
        return "payload-key"

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
