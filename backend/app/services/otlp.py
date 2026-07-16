import json
from datetime import UTC, datetime
from typing import Any

import structlog
from opentelemetry.proto.collector.trace.v1 import trace_service_pb2

log = structlog.get_logger()


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
        v = getattr(span, field, None) or span.get(field, b"")

        return v.hex() if isinstance(v, bytes) else str(v)

    def _get_str(self, span: Any, field: str) -> str:
        value = getattr(span, field, None) or span.get(field, "")
        return str(value)

    def _get_latency(self, span: Any) -> float:
        if hasattr(span, "end_time_unix_nano"):
            return float(
                (span.end_time_unix_nano - span.start_time_unix_nano) / 1_000_000
            )

        end = span.get("endTimeUnixNano", 0)
        start = span.get("startTimeUnixNano", 0)

        return float((int(end) - int(start)) / 1_000_000)

    def _get_time(self, span: Any) -> str:
        ns = getattr(span, "start_time_unix_nano", None) or int(
            span.get("startTimeUnixNano", 0)
        )

        return datetime.fromtimestamp(ns / 1e9, tz=UTC).isoformat()

    def _get_attrs(self, span: Any) -> dict[str, str]:
        attrs = getattr(span, "attributes", None) or span.get("attributes", [])
        if isinstance(attrs, list):
            return {
                a.get("key", ""): a.get("value", {}).get("stringValue", "")
                for a in attrs
            }

        return {a.key: a.value.string_value for a in attrs}
