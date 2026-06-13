import time
import uuid
from datetime import datetime, UTC

from llm_obs.decorators import _current_span_id, _current_trace_id
from llm_obs.tracer import SpanData


def patch_anthropic(client):
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
                usage = response.usage if response else None
                _get_tracer().record(
                    SpanData(
                        trace_id=trace_id,
                        span_id=span_id,
                        name="anthropic.messages.create",
                        provider="anthropic",
                        model=model,
                        input_messages=messages,
                        output=response.content[0].text
                        if response and response.content
                        else None,
                        error=error_str,
                        input_tokens=usage.input_tokens if usage else 0,
                        output_tokens=usage.output_tokens if usage else 0,
                        latency_ms=latency_ms,
                        started_at=started_at,
                        metadata={"parent_span_id": parent_span_id, "system": system},
                    )
                )

            except Exception:
                pass

    client.messages.create = traced
    return client
