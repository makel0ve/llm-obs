import asyncio
import atexit
from collections import deque
from dataclasses import dataclass, field
from datetime import UTC, datetime
from typing import Any

import structlog

from llm_obs.transport import HttpTransport, TransportDiagnostics

log = structlog.get_logger()


@dataclass
class SpanData:
    trace_id: str
    span_id: str
    name: str
    provider: str
    model: str
    input_messages: list[dict]
    parent_span_id: str | None = None
    output: str | None = None
    error: str | None = None
    input_tokens: int = 0
    output_tokens: int = 0
    latency_ms: float = 0.0
    started_at: datetime = field(default_factory=lambda: datetime.now(UTC))
    metadata: dict[str, Any] = field(default_factory=dict)


@dataclass(frozen=True)
class SDKDiagnostics:
    dropped_spans: int
    failed_flushes: int
    final_delivery_failures: int
    buffered_spans: int
    buffer_size: int | None
    last_drop_reason: str | None = None
    last_flush_reason: str | None = None


class LLMTracer:
    def __init__(
        self,
        api_key: str,
        endpoint: str,
        buffer_size: int = 500,
        flush_interval: float = 5.0,
        debug: bool = False,
    ):
        self._api_key = api_key
        self._endpoint = endpoint
        self._buffer: deque[SpanData] = deque(maxlen=buffer_size)
        self._pending_batches: deque[list[SpanData]] = deque()
        self._pending_spans = 0
        self._flush_interval = flush_interval
        self._flush_task: asyncio.Task | None = None
        self._shutting_down = False
        self._closed = False
        self._transport = HttpTransport(self._endpoint, self._api_key, debug=debug)
        self._atexit_registered = True
        self._dropped_spans = 0
        self._failed_flushes = 0
        self._final_delivery_failures = 0
        self._last_drop_reason: str | None = None

        atexit.register(self._sync_flush_on_exit)

    async def start(self) -> None:
        if self._closed:
            raise RuntimeError("llm-obs tracer is already shut down")

        if self._flush_task and not self._flush_task.done():
            return

        self._shutting_down = False
        self._flush_task = asyncio.create_task(
            self._flush_loop(), name="llm-obs-flush-loop"
        )

    async def shutdown(self, *, flush: bool = True) -> None:
        if self._closed:
            return

        self._shutting_down = True
        if self._flush_task and not self._flush_task.done():
            self._flush_task.cancel()
            try:
                await self._flush_task

            except asyncio.CancelledError:
                pass

        if flush:
            while self._has_buffered_spans():
                sent = await self._flush()
                if not sent:
                    self._final_delivery_failures += 1
                    log.warning(
                        "llm_obs_shutdown_flush_failed",
                        buffered_spans=self._buffered_spans_count(),
                        final_delivery_failures=self._final_delivery_failures,
                        flush_reason=self._flush_reason,
                    )
                    break

        else:
            self._buffer.clear()
            self._pending_batches.clear()
            self._pending_spans = 0

        await self._transport.aclose()
        if self._atexit_registered:
            try:
                atexit.unregister(self._sync_flush_on_exit)
            except ValueError:
                pass
            self._atexit_registered = False
        self._closed = True

    async def __aenter__(self) -> "LLMTracer":
        await self.start()
        return self

    async def __aexit__(self, *args) -> None:
        await self.shutdown()

    def _sync_flush_on_exit(self) -> None:
        if self._closed or not self._has_buffered_spans():
            return

        loop = None
        created_loop = False
        try:
            try:
                loop = asyncio.get_event_loop()
            except RuntimeError:
                loop = asyncio.new_event_loop()
                created_loop = True

            if loop.is_running() or loop.is_closed():
                return

            while self._has_buffered_spans():
                sent = loop.run_until_complete(self._flush())
                if not sent:
                    break

        except Exception:
            pass
        finally:
            if created_loop and loop is not None:
                loop.close()

    async def _flush_loop(self) -> None:
        while not self._shutting_down:
            await asyncio.sleep(self._flush_interval)
            await self._flush()

    async def _flush(self) -> bool:
        spans = self._pop_next_flush_batch()
        if not spans:
            return True

        sent = await self._transport.send_batch([self._span_to_dict(s) for s in spans])
        if not sent:
            self._failed_flushes += 1
            self._push_failed_batch(spans)
            return False

        return True

    def _pop_next_flush_batch(self) -> list[SpanData]:
        if self._pending_batches:
            spans = self._pending_batches.popleft()
            self._pending_spans -= len(spans)
            return spans

        active_spans: list[SpanData] = []
        while self._buffer:
            active_spans.append(self._buffer.popleft())
        return active_spans

    def _push_failed_batch(self, spans: list[SpanData]) -> None:
        self._pending_batches.appendleft(spans)
        self._pending_spans += len(spans)

    def _has_buffered_spans(self) -> bool:
        return bool(self._buffer) or self._pending_spans > 0

    def _buffered_spans_count(self) -> int:
        return len(self._buffer) + self._pending_spans

    @property
    def last_flush_diagnostics(self) -> TransportDiagnostics | None:
        return self._transport.last_diagnostics

    @property
    def sdk_diagnostics(self) -> SDKDiagnostics:
        return SDKDiagnostics(
            dropped_spans=self._dropped_spans,
            failed_flushes=self._failed_flushes,
            final_delivery_failures=self._final_delivery_failures,
            buffered_spans=self._buffered_spans_count(),
            buffer_size=self._buffer.maxlen,
            last_drop_reason=self._last_drop_reason,
            last_flush_reason=self._flush_reason,
        )

    @property
    def _flush_reason(self) -> str | None:
        diagnostics = self.last_flush_diagnostics
        return diagnostics.reason if diagnostics is not None else None

    def _span_to_dict(self, span: SpanData) -> dict:
        return {
            "span_id": span.span_id,
            "trace_id": span.trace_id,
            "parent_span_id": span.parent_span_id,
            "name": span.name,
            "provider": span.provider,
            "model": span.model,
            "input_messages": span.input_messages,
            "output": span.output,
            "error": span.error,
            "input_tokens": span.input_tokens,
            "output_tokens": span.output_tokens,
            "latency_ms": span.latency_ms,
            "started_at": span.started_at.isoformat(),
            "metadata": span.metadata,
        }

    def record(self, span: SpanData) -> None:
        if self._buffer.maxlen is not None and len(self._buffer) >= self._buffer.maxlen:
            self._dropped_spans += 1
            self._last_drop_reason = "buffer_overflow"
            log.warning(
                "llm_obs_span_dropped",
                reason="buffer_overflow",
                dropped_spans=self._dropped_spans,
                buffer_size=self._buffer.maxlen,
            )

        self._buffer.append(span)
