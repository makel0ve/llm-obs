import asyncio
import functools
import time
import traceback as tb
import uuid
import warnings
from collections.abc import Callable
from contextvars import ContextVar, Token
from datetime import UTC, datetime
from types import TracebackType
from typing import Any, ParamSpec, Self, TypeVar

P = ParamSpec("P")
T = TypeVar("T")

_current_trace_id: ContextVar[str | None] = ContextVar("trace_id", default=None)
_current_span_id: ContextVar[str | None] = ContextVar("span_id", default=None)


class ManualSpan:
    def __init__(
        self,
        name: str,
        *,
        provider: str = "custom",
        model: str = "unknown",
        input_messages: list[dict[str, Any]] | None = None,
        metadata: dict[str, Any] | None = None,
    ) -> None:
        self.name = name
        self.provider = provider
        self.model = model
        self.input_messages = input_messages or []
        self.metadata = dict(metadata or {})
        self.output: str | None = None
        self.input_tokens = 0
        self.output_tokens = 0
        self.trace_id = _current_trace_id.get() or str(uuid.uuid4())
        self.span_id = str(uuid.uuid4())
        self.parent_span_id = _current_span_id.get()
        self._trace_token: Token[str | None] | None = None
        self._span_token: Token[str | None] | None = None
        self._started_at: datetime | None = None
        self._start = 0.0

    async def __aenter__(self) -> Self:
        self.trace_id = _current_trace_id.get() or self.trace_id
        self.parent_span_id = _current_span_id.get()
        self._trace_token = _current_trace_id.set(self.trace_id)
        self._span_token = _current_span_id.set(self.span_id)
        self._started_at = datetime.now(UTC)
        self._start = time.perf_counter()
        return self

    async def __aexit__(
        self,
        exc_type: type[BaseException] | None,
        exc: BaseException | None,
        traceback: TracebackType | None,
    ) -> None:
        latency_ms = (time.perf_counter() - self._start) * 1000
        error_str = (
            "".join(tb.format_exception(exc_type, exc, traceback)) if exc else None
        )

        if self._span_token is not None:
            _current_span_id.reset(self._span_token)
        if self._trace_token is not None:
            _current_trace_id.reset(self._trace_token)

        try:
            from llm_obs import _get_or_create_tracer
            from llm_obs.tracer import SpanData

            tracer = _get_or_create_tracer()
            if tracer is not None:
                tracer.record(
                    SpanData(
                        trace_id=self.trace_id,
                        span_id=self.span_id,
                        name=self.name,
                        provider=self.provider,
                        model=self.model,
                        input_messages=self.input_messages,
                        parent_span_id=self.parent_span_id,
                        output=self.output,
                        error=error_str,
                        input_tokens=self.input_tokens,
                        output_tokens=self.output_tokens,
                        latency_ms=latency_ms,
                        started_at=self._started_at or datetime.now(UTC),
                        metadata=self.metadata,
                    )
                )

        except RuntimeError:
            pass

    def set_output(self, output: str | None) -> None:
        self.output = output

    def set_tokens(self, *, input_tokens: int = 0, output_tokens: int = 0) -> None:
        self.input_tokens = input_tokens
        self.output_tokens = output_tokens

    def update_metadata(self, metadata: dict[str, Any]) -> None:
        self.metadata.update(metadata)


def span(
    name: str,
    *,
    provider: str = "custom",
    model: str = "unknown",
    input_messages: list[dict[str, Any]] | None = None,
    metadata: dict[str, Any] | None = None,
) -> ManualSpan:
    return ManualSpan(
        name=name,
        provider=provider,
        model=model,
        input_messages=input_messages,
        metadata=metadata,
    )


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
