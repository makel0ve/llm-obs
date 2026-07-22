import json
from typing import Any, cast
from uuid import UUID, uuid4

import pytest
from fastapi import Response
from opentelemetry.proto.collector.trace.v1 import trace_service_pb2
from pydantic import ValidationError

from app.api.v1 import otlp as otlp_api
from app.api.v1.otlp import receive_otlp
from app.schemas.ingest import OTLP_ID_NAMESPACE, SpanSchema
from app.services.otlp import OTLPConverter
from tests.fixtures.otlp import (
    END_TIME_UNIX_NANO,
    PARENT_SPAN_ID_HEX,
    SPAN_ID_HEX,
    START_TIME_UNIX_NANO,
    TRACE_ID_HEX,
    representative_otlp_json_trace,
    representative_otlp_protobuf_trace,
)


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


def test_otlp_converter_parses_representative_protobuf_fixture() -> None:
    spans = OTLPConverter().parse(
        representative_otlp_protobuf_trace(),
        "application/x-protobuf",
    )

    assert spans is not None
    assert len(spans) == 1
    span = spans[0]
    assert span["trace_id"] == TRACE_ID_HEX
    assert span["span_id"] == SPAN_ID_HEX
    assert span["parent_span_id"] == PARENT_SPAN_ID_HEX
    assert span["name"] == "chat gpt-4o-mini"
    assert span["latency_ms"] == pytest.approx(
        (END_TIME_UNIX_NANO - START_TIME_UNIX_NANO) / 1_000_000
    )
    assert span["metadata"]["gen_ai.provider.name"] == "openai"
    assert span["metadata"]["gen_ai.request.model"] == "gpt-4o-mini"
    assert span["metadata"]["gen_ai.usage.input_tokens"] == ""
    assert span["metadata"]["gen_ai.usage.output_tokens"] == ""

    validated = SpanSchema(**span)
    assert validated.trace_id == str(uuid5_for(TRACE_ID_HEX))
    assert validated.span_id == str(uuid5_for(SPAN_ID_HEX))


def test_standard_otlp_json_fixture_exposes_current_camelcase_gap() -> None:
    fixture = representative_otlp_json_trace()

    spans = OTLPConverter().parse(
        json.dumps(fixture).encode(),
        "application/json",
    )

    assert spans is not None
    assert fixture["resourceSpans"][0]["scopeSpans"][0]["spans"][0]["traceId"]
    assert fixture["resourceSpans"][0]["scopeSpans"][0]["spans"][0]["spanId"]
    assert spans[0]["trace_id"] == ""
    assert spans[0]["span_id"] == ""
    assert spans[0]["parent_span_id"] is None


def test_representative_otlp_fixtures_cover_mixed_any_value_types() -> None:
    json_attributes = representative_otlp_json_trace()["resourceSpans"][0][
        "scopeSpans"
    ][0]["spans"][0]["attributes"]
    json_value_types = {
        next(iter(attribute["value"].keys())) for attribute in json_attributes
    }

    proto_request = trace_service_pb2.ExportTraceServiceRequest()
    proto_request.ParseFromString(representative_otlp_protobuf_trace())
    proto_attributes = (
        proto_request.resource_spans[0].scope_spans[0].spans[0].attributes
    )
    proto_value_types = {
        attribute.value.WhichOneof("value") for attribute in proto_attributes
    }

    assert {
        "stringValue",
        "intValue",
        "doubleValue",
        "boolValue",
        "arrayValue",
        "kvlistValue",
    }.issubset(json_value_types)
    assert {
        "string_value",
        "int_value",
        "double_value",
        "bool_value",
        "array_value",
        "kvlist_value",
    }.issubset(proto_value_types)


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
