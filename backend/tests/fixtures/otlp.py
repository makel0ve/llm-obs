from __future__ import annotations

from copy import deepcopy
from typing import Any, cast

from opentelemetry.proto.collector.trace.v1 import trace_service_pb2
from opentelemetry.proto.common.v1 import common_pb2
from opentelemetry.proto.resource.v1 import resource_pb2
from opentelemetry.proto.trace.v1 import trace_pb2

TRACE_ID_HEX = "0af7651916cd43dd8448eb211c80319c"
SPAN_ID_HEX = "b7ad6b7169203331"
PARENT_SPAN_ID_HEX = "00f067aa0ba902b7"
START_TIME_UNIX_NANO = 1_784_199_600_123_000_000
END_TIME_UNIX_NANO = START_TIME_UNIX_NANO + 243_000_000


def representative_otlp_json_trace() -> dict[str, Any]:
    return deepcopy(
        {
            "resourceSpans": [
                {
                    "resource": {
                        "attributes": [
                            _json_attr("service.name", {"stringValue": "orders-api"}),
                            _json_attr(
                                "deployment.environment",
                                {"stringValue": "test"},
                            ),
                        ]
                    },
                    "scopeSpans": [
                        {
                            "scope": {
                                "name": "opentelemetry.instrumentation.openai",
                                "version": "0.1.0",
                            },
                            "spans": [
                                {
                                    "traceId": TRACE_ID_HEX,
                                    "spanId": SPAN_ID_HEX,
                                    "parentSpanId": PARENT_SPAN_ID_HEX,
                                    "name": "chat gpt-4o-mini",
                                    "kind": 3,
                                    "startTimeUnixNano": str(START_TIME_UNIX_NANO),
                                    "endTimeUnixNano": str(END_TIME_UNIX_NANO),
                                    "attributes": [
                                        _json_attr(
                                            "gen_ai.provider.name",
                                            {"stringValue": "openai"},
                                        ),
                                        _json_attr(
                                            "gen_ai.request.model",
                                            {"stringValue": "gpt-4o-mini"},
                                        ),
                                        _json_attr(
                                            "gen_ai.usage.input_tokens",
                                            {"intValue": "17"},
                                        ),
                                        _json_attr(
                                            "gen_ai.usage.output_tokens",
                                            {"intValue": "23"},
                                        ),
                                        _json_attr(
                                            "llmobs.float_score",
                                            {"doubleValue": 0.75},
                                        ),
                                        _json_attr(
                                            "llmobs.cache_hit",
                                            {"boolValue": False},
                                        ),
                                        _json_attr(
                                            "llmobs.labels",
                                            {
                                                "arrayValue": {
                                                    "values": [
                                                        {"stringValue": "chat"},
                                                        {"stringValue": "ci"},
                                                    ]
                                                }
                                            },
                                        ),
                                        _json_attr(
                                            "llmobs.options",
                                            {
                                                "kvlistValue": {
                                                    "values": [
                                                        _json_attr(
                                                            "route",
                                                            {"stringValue": "/chat"},
                                                        )
                                                    ]
                                                }
                                            },
                                        ),
                                    ],
                                    "status": {
                                        "code": 2,
                                        "message": "provider timeout",
                                    },
                                }
                            ],
                        }
                    ],
                }
            ]
        }
    )


def representative_otlp_protobuf_trace() -> bytes:
    request = trace_service_pb2.ExportTraceServiceRequest()
    resource_span = request.resource_spans.add()
    resource_span.resource.CopyFrom(
        resource_pb2.Resource(
            attributes=[
                _proto_attr("service.name", string_value="orders-api"),
                _proto_attr("deployment.environment", string_value="test"),
            ]
        )
    )

    scope_span = resource_span.scope_spans.add()
    scope_span.scope.name = "opentelemetry.instrumentation.openai"
    scope_span.scope.version = "0.1.0"

    span = scope_span.spans.add()
    span.trace_id = bytes.fromhex(TRACE_ID_HEX)
    span.span_id = bytes.fromhex(SPAN_ID_HEX)
    span.parent_span_id = bytes.fromhex(PARENT_SPAN_ID_HEX)
    span.name = "chat gpt-4o-mini"
    span.kind = trace_pb2.Span.SPAN_KIND_CLIENT
    span.start_time_unix_nano = START_TIME_UNIX_NANO
    span.end_time_unix_nano = END_TIME_UNIX_NANO
    span.attributes.extend(
        [
            _proto_attr("gen_ai.provider.name", string_value="openai"),
            _proto_attr("gen_ai.request.model", string_value="gpt-4o-mini"),
            _proto_attr("gen_ai.usage.input_tokens", int_value=17),
            _proto_attr("gen_ai.usage.output_tokens", int_value=23),
            _proto_attr("llmobs.float_score", double_value=0.75),
            _proto_attr("llmobs.cache_hit", bool_value=False),
            _proto_attr(
                "llmobs.labels",
                array_value=common_pb2.ArrayValue(
                    values=[
                        common_pb2.AnyValue(string_value="chat"),
                        common_pb2.AnyValue(string_value="ci"),
                    ]
                ),
            ),
            _proto_attr(
                "llmobs.options",
                kvlist_value=common_pb2.KeyValueList(
                    values=[_proto_attr("route", string_value="/chat")]
                ),
            ),
        ]
    )
    span.status.code = trace_pb2.Status.STATUS_CODE_ERROR
    span.status.message = "provider timeout"

    return cast(bytes, request.SerializeToString())


def _json_attr(key: str, value: dict[str, Any]) -> dict[str, Any]:
    return {"key": key, "value": value}


def _proto_attr(
    key: str,
    *,
    string_value: str | None = None,
    int_value: int | None = None,
    double_value: float | None = None,
    bool_value: bool | None = None,
    array_value: common_pb2.ArrayValue | None = None,
    kvlist_value: common_pb2.KeyValueList | None = None,
) -> common_pb2.KeyValue:
    value = common_pb2.AnyValue()
    if string_value is not None:
        value.string_value = string_value
    elif int_value is not None:
        value.int_value = int_value
    elif double_value is not None:
        value.double_value = double_value
    elif bool_value is not None:
        value.bool_value = bool_value
    elif array_value is not None:
        value.array_value.CopyFrom(array_value)
    elif kvlist_value is not None:
        value.kvlist_value.CopyFrom(kvlist_value)

    return common_pb2.KeyValue(key=key, value=value)
