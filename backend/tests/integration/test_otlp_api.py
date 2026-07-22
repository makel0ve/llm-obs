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
    assert span["provider"] == "openai"
    assert span["model"] == "gpt-4o-mini"
    assert span["input_tokens"] == 17
    assert span["output_tokens"] == 23
    assert span["error"] == "provider timeout"
    assert span["metadata"]["gen_ai.provider.name"] == "openai"
    assert span["metadata"]["gen_ai.request.model"] == "gpt-4o-mini"
    assert span["metadata"]["gen_ai.usage.input_tokens"] == 17
    assert span["metadata"]["gen_ai.usage.output_tokens"] == 23
    assert span["metadata"]["llmobs.float_score"] == 0.75
    assert span["metadata"]["llmobs.cache_hit"] is False
    assert span["metadata"]["llmobs.labels"] == ["chat", "ci"]
    assert span["metadata"]["llmobs.options"] == {"route": "/chat"}

    validated = SpanSchema(**span)
    assert validated.trace_id == str(uuid5_for(TRACE_ID_HEX))
    assert validated.span_id == str(uuid5_for(SPAN_ID_HEX))


def test_otlp_converter_parses_standard_json_camelcase_fixture() -> None:
    fixture = representative_otlp_json_trace()

    spans = OTLPConverter().parse(
        json.dumps(fixture).encode(),
        "application/json",
    )

    assert spans is not None
    assert fixture["resourceSpans"][0]["scopeSpans"][0]["spans"][0]["traceId"]
    assert fixture["resourceSpans"][0]["scopeSpans"][0]["spans"][0]["spanId"]
    span = spans[0]
    assert span["trace_id"] == TRACE_ID_HEX
    assert span["span_id"] == SPAN_ID_HEX
    assert span["parent_span_id"] == PARENT_SPAN_ID_HEX
    assert span["name"] == "chat gpt-4o-mini"
    assert span["latency_ms"] == pytest.approx(
        (END_TIME_UNIX_NANO - START_TIME_UNIX_NANO) / 1_000_000
    )
    assert span["provider"] == "openai"
    assert span["model"] == "gpt-4o-mini"
    assert span["input_tokens"] == 17
    assert span["output_tokens"] == 23
    assert span["error"] == "provider timeout"
    assert span["metadata"]["gen_ai.provider.name"] == "openai"
    assert span["metadata"]["gen_ai.request.model"] == "gpt-4o-mini"
    assert span["metadata"]["gen_ai.usage.input_tokens"] == 17
    assert span["metadata"]["gen_ai.usage.output_tokens"] == 23
    assert span["metadata"]["llmobs.float_score"] == 0.75
    assert span["metadata"]["llmobs.cache_hit"] is False
    assert span["metadata"]["llmobs.labels"] == ["chat", "ci"]
    assert span["metadata"]["llmobs.options"] == {"route": "/chat"}

    validated = SpanSchema(**span)
    assert validated.trace_id == str(uuid5_for(TRACE_ID_HEX))
    assert validated.span_id == str(uuid5_for(SPAN_ID_HEX))


def test_otlp_converter_preserves_snake_case_json_compatibility() -> None:
    fixture = representative_otlp_json_trace()
    json_span = fixture["resourceSpans"][0]["scopeSpans"][0]["spans"][0]
    json_span["trace_id"] = json_span.pop("traceId")
    json_span["span_id"] = json_span.pop("spanId")
    json_span["parent_span_id"] = json_span.pop("parentSpanId")
    json_span["start_time_unix_nano"] = json_span.pop("startTimeUnixNano")
    json_span["end_time_unix_nano"] = json_span.pop("endTimeUnixNano")

    spans = OTLPConverter().parse(
        json.dumps(fixture).encode(),
        "application/json",
    )

    assert spans is not None
    assert spans[0]["trace_id"] == TRACE_ID_HEX
    assert spans[0]["span_id"] == SPAN_ID_HEX
    assert spans[0]["parent_span_id"] == PARENT_SPAN_ID_HEX


def test_otlp_converter_uses_defaults_for_unknown_semantic_conventions() -> None:
    fixture = representative_otlp_json_trace()
    json_span = fixture["resourceSpans"][0]["scopeSpans"][0]["spans"][0]
    json_span["attributes"] = [
        {"key": "custom.provider", "value": {"stringValue": "other"}},
        {"key": "custom.model", "value": {"stringValue": "other-model"}},
        {"key": "custom.input_tokens", "value": {"intValue": "9"}},
    ]

    spans = OTLPConverter().parse(
        json.dumps(fixture).encode(),
        "application/json",
    )

    assert spans is not None
    assert spans[0]["provider"] == "custom"
    assert spans[0]["model"] == "unknown"
    assert spans[0]["input_tokens"] == 0
    assert spans[0]["output_tokens"] == 0
    assert spans[0]["metadata"]["custom.input_tokens"] == 9


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
    result_response = Response()

    result = await receive_otlp(
        request=cast(Any, FakeRequest(b"{}")),
        response=result_response,
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
    result_response = Response()

    result = await receive_otlp(
        request=cast(Any, FakeRequest(b"{}")),
        response=result_response,
        project={"id": str(uuid4())},
        service=cast(Any, service),
        rate_limiter=cast(Any, FakeRateLimiter()),
    )

    assert len(service.accepted) == 1
    assert result_response.status_code == 200
    assert result["partialSuccess"]["rejectedSpans"] == 1
    assert "valid UUID or OTLP hex ID" in result["partialSuccess"]["errorMessage"]


@pytest.mark.asyncio
async def test_receive_otlp_returns_bad_request_for_malformed_payload() -> None:
    service = FakeIngestService()
    result_response = Response()

    result = await receive_otlp(
        request=cast(Any, FakeRequest(b"{")),
        response=result_response,
        project={"id": str(uuid4())},
        service=cast(Any, service),
        rate_limiter=cast(Any, FakeRateLimiter()),
    )

    assert service.accepted == []
    assert result_response.status_code == 400
    assert result == {"error": "Unable to parse OTLP trace export"}


def uuid5_for(value: str) -> UUID:
    from uuid import uuid5

    return uuid5(OTLP_ID_NAMESPACE, value)
