import asyncio
import functools
import time
import traceback as tb
import uuid
import warnings
from contextvars import ContextVar
from datetime import datetime, UTC
from typing import Callable, TypeVar, ParamSpec, Any


P = ParamSpec("P")
T = TypeVar("T")

_current_trace_id: ContextVar[str | None] = ContextVar("trace_id", default=None)
_current_span_id: ContextVar[str | None] = ContextVar("span_id", default=None)


def trace(name: str | None = None, metadata: dict | None = None):
    def decorator(func: Callable[P, T]) -> Callable[P, Any]:
        func_name = name or f"{func.__module__}.{func.__qualname__}"

        if not asyncio.iscoroutinefunction(func):
            warnings.warn(
                f"@trace on sync function '{func_name}' has no effect. Use async.",
                stacklevel=2,
            )
            return func

        @functools.wraps(func)
        async def wrapper(*args: P.args, **kwargs: P.kwargs) -> T:
            from llm_obs import _get_or_create_tracer
            from llm_obs.tracer import SpanData

            span_id = str(uuid.uuid4())
            trace_id = _current_trace_id.get() or str(uuid.uuid4())
            parent_span_id = _current_span_id.get()

            trace_token = _current_trace_id.set(trace_id)
            span_token = _current_span_id.set(span_id)
            started_at = datetime.now(UTC)
            start = time.perf_counter()
            error_str = None

            try:
                return await func(*args, **kwargs)

            except Exception:
                error_str = tb.format_exc()
                raise

            finally:
                latency_ms = (time.perf_counter() - start) * 1000
                _current_trace_id.reset(trace_token)
                _current_span_id.reset(span_token)

                try:
                    tracer = _get_or_create_tracer()
                    if tracer is not None:
                        tracer.record(
                            SpanData(
                                trace_id=trace_id,
                                span_id=span_id,
                                name=func_name,
                                provider="custom",
                                model="unknown",
                                input_messages=[],
                                parent_span_id=parent_span_id,
                                error=error_str,
                                latency_ms=latency_ms,
                                started_at=started_at,
                                metadata=metadata or {},
                            )
                        )

                except RuntimeError:
                    pass

        return wrapper  # type: ignore[return-value]

    return decorator
