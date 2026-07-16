from typing import Any, cast
from uuid import UUID, uuid4

import pytest
from fastapi import Response
from pydantic import ValidationError

from app.api.v1 import otlp as otlp_api
from app.api.v1.otlp import receive_otlp
from app.schemas.ingest import OTLP_ID_NAMESPACE, SpanSchema


@pytest.fixture(autouse=True, scope="session")
def patch_app_engine() -> None:
    return None


class FakeRateLimiter:
    async def check(self, project_id: str, response: Response) -> None:
        response.headers["X-RateLimit-Limit"] = "1000"


class FakeRequest:
    def __init__(self, body: bytes, content_type: str = "application/json") -> None:
        self.headers = {"content-type": content_type}
        self._body = body

    async def body(self) -> bytes:
        return self._body


class FakeIngestService:
    def __init__(self) -> None:
        self.accepted: list[SpanSchema] = []

    async def accept_batch(self, project_id: str, spans: list[SpanSchema]) -> object:
        self.accepted.extend(spans)
        return object()


def _span(
    span_id: str, trace_id: str, parent_span_id: str | None = None
) -> dict[str, Any]:
    return {
        "span_id": span_id,
        "trace_id": trace_id,
        "parent_span_id": parent_span_id,
        "name": "otel-span",
        "provider": "custom",
        "model": "unknown",
        "input_tokens": 0,
        "output_tokens": 0,
        "latency_ms": 1,
        "started_at": "2026-07-16T10:00:00Z",
        "metadata": {},
    }


def test_span_schema_normalizes_otlp_hex_ids() -> None:
    trace_id = "0af7651916cd43dd8448eb211c80319c"
    span_id = "b7ad6b7169203331"
    parent_span_id = "00f067aa0ba902b7"

    span = SpanSchema(**_span(span_id, trace_id, parent_span_id))

    assert span.trace_id == str(uuid5_for(trace_id))
    assert span.span_id == str(uuid5_for(span_id))
    assert span.parent_span_id == str(uuid5_for(parent_span_id))


def test_span_schema_rejects_malformed_otlp_ids() -> None:
    with pytest.raises(ValidationError, match="valid UUID or OTLP hex ID"):
        SpanSchema(**_span("not-a-hex-id", "0af7651916cd43dd8448eb211c80319c"))


@pytest.mark.asyncio
async def test_receive_otlp_accepts_valid_spans_without_partial_success(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    service = FakeIngestService()
    spans = [_span("b7ad6b7169203331", "0af7651916cd43dd8448eb211c80319c")]

    class FakeConverter:
        def parse(self, body: bytes, content_type: str) -> list[dict[str, Any]]:
            return spans

    monkeypatch.setattr(otlp_api, "OTLPConverter", FakeConverter)

    result = await receive_otlp(
        request=cast(Any, FakeRequest(b"{}")),
        response=Response(),
        project={"id": str(uuid4())},
        service=cast(Any, service),
        rate_limiter=cast(Any, FakeRateLimiter()),
    )

    assert len(service.accepted) == 1
    assert result == {}


@pytest.mark.asyncio
async def test_receive_otlp_accepts_valid_spans_and_reports_rejected(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    service = FakeIngestService()
    spans = [
        _span("b7ad6b7169203331", "0af7651916cd43dd8448eb211c80319c"),
        _span("bad-span-id", "0af7651916cd43dd8448eb211c80319c"),
    ]

    class FakeConverter:
        def parse(self, body: bytes, content_type: str) -> list[dict[str, Any]]:
            return spans

    monkeypatch.setattr(otlp_api, "OTLPConverter", FakeConverter)

    result = await receive_otlp(
        request=cast(Any, FakeRequest(b"{}")),
        response=Response(),
        project={"id": str(uuid4())},
        service=cast(Any, service),
        rate_limiter=cast(Any, FakeRateLimiter()),
    )

    assert len(service.accepted) == 1
    assert result["partialSuccess"]["rejectedSpans"] == 1
    assert "valid UUID or OTLP hex ID" in result["partialSuccess"]["errorMessage"]


@pytest.mark.asyncio
async def test_receive_otlp_reports_parse_failure(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    service = FakeIngestService()

    class FakeConverter:
        def parse(self, body: bytes, content_type: str) -> None:
            return None

    monkeypatch.setattr(otlp_api, "OTLPConverter", FakeConverter)

    result = await receive_otlp(
        request=cast(Any, FakeRequest(b"{")),
        response=Response(),
        project={"id": str(uuid4())},
        service=cast(Any, service),
        rate_limiter=cast(Any, FakeRateLimiter()),
    )

    assert service.accepted == []
    assert result == {
        "partialSuccess": {
            "rejectedSpans": 1,
            "errorMessage": "Unable to parse OTLP trace export",
        }
    }


def uuid5_for(value: str) -> UUID:
    from uuid import uuid5

    return uuid5(OTLP_ID_NAMESPACE, value)
