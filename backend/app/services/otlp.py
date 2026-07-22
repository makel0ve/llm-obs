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
                    spans.append(
                        {
                            "span_id": self._get_id(span, "span_id"),
                            "trace_id": self._get_id(span, "trace_id"),
                            "parent_span_id": self._get_id(span, "parent_span_id")
                            or None,
                            "name": self._get_str(span, "name"),
                            "provider": "custom",
                            "model": "unknown",
                            "input_tokens": 0,
                            "output_tokens": 0,
                            "latency_ms": self._get_latency(span),
                            "started_at": self._get_time(span),
                            "metadata": self._get_attrs(span),
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

    def _get_attrs(self, span: Any) -> dict[str, str]:
        attrs = getattr(span, "attributes", None) or span.get("attributes", [])
        if isinstance(attrs, list):
            return {
                a.get("key", ""): a.get("value", {}).get("stringValue", "")
                for a in attrs
            }

        return {a.key: a.value.string_value for a in attrs}

    def _get_field(self, value: Any, field: str) -> Any:
        if hasattr(value, field):
            return getattr(value, field)

        if isinstance(value, dict):
            json_field = JSON_FIELD_ALIASES.get(field, field)
            return value.get(json_field, value.get(field))

        return None
