import time
import uuid
from datetime import UTC, datetime
from typing import Any

import structlog

from llm_obs.decorators import _current_span_id, _current_trace_id
from llm_obs.tracer import SpanData

_PATCHED_ATTR = "__llm_obs_anthropic_patched__"
log = structlog.get_logger()


def _get_value(obj, name, default=None):
    if obj is None:
        return default
    if isinstance(obj, dict):
        return obj.get(name, default)
    return getattr(obj, name, default)


def _extract_usage(response) -> tuple[int, int]:
    usage = _get_value(response, "usage")
    return (
        int(_get_value(usage, "input_tokens", 0) or 0),
        int(_get_value(usage, "output_tokens", 0) or 0),
    )


def _extract_output(response) -> str | None:
    content = _get_value(response, "content", []) or []
    if not content:
        return None

    return _get_value(content[0], "text")


def _extract_stream_delta(event) -> str:
    delta = _get_value(event, "delta")
    text = _get_value(delta, "text")
    if text:
        return str(text)

    content_block = _get_value(event, "content_block")
    text = _get_value(content_block, "text")
    return str(text) if text else ""


def _extract_message_start_usage(event) -> tuple[int, int]:
    message = _get_value(event, "message")
    usage = _get_value(message, "usage")
    return (
        int(_get_value(usage, "input_tokens", 0) or 0),
        int(_get_value(usage, "output_tokens", 0) or 0),
    )


class _TracedAnthropicStream:
    def __init__(
        self,
        stream,
        *,
        trace_id: str,
        span_id: str,
        parent_span_id: str | None,
        model: str,
        messages: list,
        system,
        started_at: datetime,
        start: float,
    ) -> None:
        self._stream = stream
        self._trace_id = trace_id
        self._span_id = span_id
        self._parent_span_id = parent_span_id
        self._model = model
        self._messages = messages
        self._system = system
        self._started_at = started_at
        self._start = start
        self._output_parts: list[str] = []
        self._input_tokens = 0
        self._output_tokens = 0
        self._recorded = False

    def __aiter__(self):
        return self._iterate()

    def __getattr__(self, name: str) -> Any:
        return getattr(self._stream, name)

    async def aclose(self) -> None:
        close = getattr(self._stream, "aclose", None)
        if close is not None:
            await close()
        self._record(error_str=None, completed=False)

    async def _iterate(self):
        error_str = None
        completed = False
        try:
            async for event in self._stream:
                self._capture_event(event)
                yield event
            completed = True

        except Exception as exc:
            error_str = str(exc)
            raise

        finally:
            self._record(error_str=error_str, completed=completed)

    def _capture_event(self, event) -> None:
        delta = _extract_stream_delta(event)
        if delta:
            self._output_parts.append(delta)

        start_input_tokens, start_output_tokens = _extract_message_start_usage(event)
        if start_input_tokens or start_output_tokens:
            self._input_tokens = start_input_tokens
            self._output_tokens = start_output_tokens

        usage = _get_value(event, "usage")
        if usage is not None:
            output_tokens = int(_get_value(usage, "output_tokens", 0) or 0)
            if output_tokens:
                self._output_tokens = output_tokens

    def _record(self, *, error_str: str | None, completed: bool) -> None:
        if self._recorded:
            return

        self._recorded = True
        latency_ms = (time.perf_counter() - self._start) * 1000
        try:
            from llm_obs import _get_tracer

            _get_tracer().record(
                SpanData(
                    trace_id=self._trace_id,
                    span_id=self._span_id,
                    name="anthropic.messages.create",
                    provider="anthropic",
                    model=self._model,
                    input_messages=self._messages,
                    parent_span_id=self._parent_span_id,
                    output="".join(self._output_parts) or None,
                    error=error_str,
                    input_tokens=self._input_tokens,
                    output_tokens=self._output_tokens,
                    latency_ms=latency_ms,
                    started_at=self._started_at,
                    metadata={
                        "system": self._system,
                        "stream": True,
                        "stream_complete": completed,
                    },
                )
            )

        except Exception as exc:  # noqa: BLE001
            log.debug("llm_obs_anthropic_stream_record_failed", error=str(exc))


def patch_anthropic(client):
    if getattr(client.messages.create, _PATCHED_ATTR, False):
        return client

    original = client.messages.create

    async def traced(*args, **kwargs):
        from llm_obs import _get_tracer

        span_id = str(uuid.uuid4())
        trace_id = _current_trace_id.get() or str(uuid.uuid4())
        parent_span_id = _current_span_id.get()
        span_token = _current_span_id.set(span_id)
        trace_token = _current_trace_id.set(trace_id)
        system = kwargs.get("system")
        messages = kwargs.get("messages", [])
        model = kwargs.get("model", "unknown")
        started_at = datetime.now(UTC)
        start = time.perf_counter()
        error_str = None
        response = None
        is_stream = bool(kwargs.get("stream"))
        stream_response = None

        try:
            response = await original(*args, **kwargs)
            if is_stream and hasattr(response, "__aiter__"):
                stream_response = _TracedAnthropicStream(
                    response,
                    trace_id=trace_id,
                    span_id=span_id,
                    parent_span_id=parent_span_id,
                    model=model,
                    messages=messages,
                    system=system,
                    started_at=started_at,
                    start=start,
                )
                return stream_response

            return response

        except Exception as e:
            error_str = str(e)
            raise

        finally:
            latency_ms = (time.perf_counter() - start) * 1000

            _current_span_id.reset(span_token)
            _current_trace_id.reset(trace_token)

            if stream_response is None:
                try:
                    input_tokens, output_tokens = _extract_usage(response)
                    _get_tracer().record(
                        SpanData(
                            trace_id=trace_id,
                            span_id=span_id,
                            name="anthropic.messages.create",
                            provider="anthropic",
                            model=model,
                            input_messages=messages,
                            parent_span_id=parent_span_id,
                            output=_extract_output(response),
                            error=error_str,
                            input_tokens=input_tokens,
                            output_tokens=output_tokens,
                            latency_ms=latency_ms,
                            started_at=started_at,
                            metadata={"system": system},
                        )
                    )

                except Exception as exc:  # noqa: BLE001
                    log.debug("llm_obs_anthropic_record_failed", error=str(exc))

    setattr(traced, _PATCHED_ATTR, True)
    client.messages.create = traced
    return client
