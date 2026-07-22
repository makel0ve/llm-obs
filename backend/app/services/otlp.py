import json
from datetime import UTC, datetime
from typing import Any

import structlog
from opentelemetry.proto.collector.trace.v1 import trace_service_pb2

log = structlog.get_logger()


JSON_FIELD_ALIASES = {
    "trace_id": "traceId",
    "span_id": "spanId",
    "parent_span_id": "parentSpanId",
    "start_time_unix_nano": "startTimeUnixNano",
    "end_time_unix_nano": "endTimeUnixNano",
}

GENAI_PROVIDER_ATTRIBUTES = ("gen_ai.provider.name", "gen_ai.system")
GENAI_MODEL_ATTRIBUTES = ("gen_ai.response.model", "gen_ai.request.model")
GENAI_INPUT_TOKEN_ATTRIBUTES = (
    "gen_ai.usage.input_tokens",
    "gen_ai.usage.prompt_tokens",
)
GENAI_OUTPUT_TOKEN_ATTRIBUTES = (
    "gen_ai.usage.output_tokens",
    "gen_ai.usage.completion_tokens",
)


class OTLPConverter:
    def parse(self, body: bytes, content_type: str) -> list[dict[str, Any]] | None:
        try:
            if "application/x-protobuf" in content_type:
                return self._parse_proto(body)

            return self._parse_json(body)

        except Exception as e:
            log.warning("otlp_parse_failed", error=str(e))
            return None

    def _parse_proto(self, body: bytes) -> list[dict[str, Any]]:
        req = trace_service_pb2.ExportTraceServiceRequest()
        req.ParseFromString(body)

        return self._extract_spans(req.resource_spans)

    def _parse_json(self, body: bytes) -> list[dict[str, Any]]:
        data = json.loads(body)

        return self._extract_spans(data.get("resourceSpans", []))

    def _extract_spans(self, resource_spans: Any) -> list[dict[str, Any]]:
        spans = []
        for rs in resource_spans:
            for ss in (
                rs.scope_spans
                if hasattr(rs, "scope_spans")
                else rs.get("scopeSpans", [])
            ):
                for span in ss.spans if hasattr(ss, "spans") else ss.get("spans", []):
                    attrs = self._get_attrs(span)
                    spans.append(
                        {
                            "span_id": self._get_id(span, "span_id"),
                            "trace_id": self._get_id(span, "trace_id"),
                            "parent_span_id": self._get_id(span, "parent_span_id")
                            or None,
                            "name": self._get_str(span, "name"),
                            "provider": self._get_attr_str(
                                attrs,
                                GENAI_PROVIDER_ATTRIBUTES,
                                default="custom",
                            ),
                            "model": self._get_attr_str(
                                attrs,
                                GENAI_MODEL_ATTRIBUTES,
                                default="unknown",
                            ),
                            "input_tokens": self._get_attr_int(
                                attrs,
                                GENAI_INPUT_TOKEN_ATTRIBUTES,
                            ),
                            "output_tokens": self._get_attr_int(
                                attrs,
                                GENAI_OUTPUT_TOKEN_ATTRIBUTES,
                            ),
                            "latency_ms": self._get_latency(span),
                            "started_at": self._get_time(span),
                            "metadata": attrs,
                        }
                    )

        return spans

    def _get_id(self, span: Any, field: str) -> str:
        v = self._get_field(span, field)
        if v in (None, b"", ""):
            return ""

        return v.hex() if isinstance(v, bytes) else str(v)

    def _get_str(self, span: Any, field: str) -> str:
        value = self._get_field(span, field)
        return "" if value is None else str(value)

    def _get_latency(self, span: Any) -> float:
        if hasattr(span, "end_time_unix_nano"):
            return float(
                (span.end_time_unix_nano - span.start_time_unix_nano) / 1_000_000
            )

        end = self._get_field(span, "end_time_unix_nano") or 0
        start = self._get_field(span, "start_time_unix_nano") or 0

        return float((int(end) - int(start)) / 1_000_000)

    def _get_time(self, span: Any) -> str:
        ns = int(self._get_field(span, "start_time_unix_nano") or 0)

        return datetime.fromtimestamp(ns / 1e9, tz=UTC).isoformat()

    def _get_attrs(self, span: Any) -> dict[str, Any]:
        attrs = getattr(span, "attributes", None) or span.get("attributes", [])
        if isinstance(attrs, list):
            return {
                a.get("key", ""): self._decode_any_value(a.get("value", {}))
                for a in attrs
            }

        return {a.key: self._decode_any_value(a.value) for a in attrs}

    def _get_field(self, value: Any, field: str) -> Any:
        if hasattr(value, field):
            return getattr(value, field)

        if isinstance(value, dict):
            json_field = JSON_FIELD_ALIASES.get(field, field)
            return value.get(json_field, value.get(field))

        return None

    def _decode_any_value(self, value: Any) -> Any:
        if isinstance(value, dict):
            if "stringValue" in value:
                return value["stringValue"]
            if "boolValue" in value:
                return value["boolValue"]
            if "intValue" in value:
                return self._parse_int(value["intValue"], default=0)
            if "doubleValue" in value:
                return float(value["doubleValue"])
            if "arrayValue" in value:
                values = value["arrayValue"].get("values", [])
                return [self._decode_any_value(item) for item in values]
            if "kvlistValue" in value:
                values = value["kvlistValue"].get("values", [])
                return {
                    item.get("key", ""): self._decode_any_value(item.get("value", {}))
                    for item in values
                }
            if "bytesValue" in value:
                return str(value["bytesValue"])
            return None

        active_field = value.WhichOneof("value")
        if active_field == "array_value":
            return [self._decode_any_value(item) for item in value.array_value.values]
        if active_field == "kvlist_value":
            return {
                item.key: self._decode_any_value(item.value)
                for item in value.kvlist_value.values
            }
        if active_field == "bytes_value":
            return value.bytes_value.hex()
        if active_field is None:
            return None

        return getattr(value, active_field)

    def _get_attr_str(
        self,
        attrs: dict[str, Any],
        names: tuple[str, ...],
        *,
        default: str,
    ) -> str:
        for name in names:
            value = attrs.get(name)
            if value not in (None, ""):
                return str(value)

        return default

    def _get_attr_int(self, attrs: dict[str, Any], names: tuple[str, ...]) -> int:
        for name in names:
            if name in attrs:
                return self._parse_int(attrs[name], default=0)

        return 0

    def _parse_int(self, value: Any, *, default: int) -> int:
        try:
            return int(value)
        except (TypeError, ValueError):
            return default
