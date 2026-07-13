import time
import uuid
from datetime import datetime, UTC

from llm_obs.decorators import _current_span_id, _current_trace_id
from llm_obs.tracer import SpanData


def _get_value(obj, name, default=None):
    if obj is None:
        return default
    if isinstance(obj, dict):
        return obj.get(name, default)
    return getattr(obj, name, default)


def _extract_usage(response) -> tuple[int, int]:
    usage = _get_value(response, "usage")
    return (
        int(_get_value(usage, "prompt_tokens", 0) or 0),
        int(_get_value(usage, "completion_tokens", 0) or 0),
    )


def _extract_output(response) -> str | None:
    choices = _get_value(response, "choices", []) or []
    if not choices:
        return None

    message = _get_value(choices[0], "message")
    return _get_value(message, "content")


def patch_openai(client):
    original = client.chat.completions.create

    async def traced(*args, **kwargs):
        from llm_obs import _get_tracer

        span_id = str(uuid.uuid4())
        trace_id = _current_trace_id.get() or str(uuid.uuid4())
        parent_span_id = _current_span_id.get()
        span_token = _current_span_id.set(span_id)
        trace_token = _current_trace_id.set(trace_id)
        messages = kwargs.get("messages", [])
        model = kwargs.get("model", "unknown")
        started_at = datetime.now(UTC)
        start = time.perf_counter()
        error_str = None
        response = None

        try:
            response = await original(*args, **kwargs)
            return response

        except Exception as e:
            error_str = str(e)
            raise

        finally:
            latency_ms = (time.perf_counter() - start) * 1000

            _current_span_id.reset(span_token)
            _current_trace_id.reset(trace_token)

            try:
                input_tokens, output_tokens = _extract_usage(response)
                _get_tracer().record(
                    SpanData(
                        trace_id=trace_id,
                        span_id=span_id,
                        name="openai.chat.completions.create",
                        provider="openai",
                        model=model,
                        input_messages=messages,
                        parent_span_id=parent_span_id,
                        output=_extract_output(response),
                        error=error_str,
                        input_tokens=input_tokens,
                        output_tokens=output_tokens,
                        latency_ms=latency_ms,
                        started_at=started_at,
                    )
                )

            except Exception:
                pass

    client.chat.completions.create = traced
    return client
