import asyncio
import atexit
from collections import deque
from dataclasses import dataclass, field
from datetime import datetime, UTC
from typing import Any

from llm_obs.transport import HttpTransport


@dataclass
class SpanData:
    trace_id: str
    span_id: str
    name: str
    provider: str
    model: str
    input_messages: list[dict]
    output: str | None = None
    error: str | None = None
    input_tokens: int = 0
    output_tokens: int = 0
    latency_ms: float = 0.0
    started_at: datetime = field(default_factory=lambda: datetime.now(UTC))
    metadata: dict[str, Any] = field(default_factory=dict)


class LLMTracer:
    def __init__(
        self,
        api_key: str,
        endpoint: str,
        buffer_size: int = 500,
        flush_interval: float = 5.0,
    ):
        self._api_key = api_key
        self._endpoint = endpoint
        self._buffer: deque[SpanData] = deque(maxlen=buffer_size)
        self._flush_interval = flush_interval
        self._flush_task: asyncio.Task | None = None
        self._shutting_down = False
        self._closed = False
        self._transport = HttpTransport(self._endpoint, self._api_key)

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
            await self._flush()

        else:
            self._buffer.clear()

        await self._transport.aclose()
        self._closed = True

    async def __aenter__(self) -> "LLMTracer":
        await self.start()
        return self

    async def __aexit__(self, *args) -> None:
        await self.shutdown()

    def _sync_flush_on_exit(self) -> None:
        if self._closed or not self._buffer:
            return

        try:
            loop = asyncio.get_event_loop()
            if not loop.is_closed():
                loop.run_until_complete(self._flush())

        except Exception:
            pass

    async def _flush_loop(self) -> None:
        while not self._shutting_down:
            await asyncio.sleep(self._flush_interval)
            await self._flush()

    async def _flush(self) -> None:
        if not self._buffer:
            return

        spans = []
        while self._buffer:
            spans.append(self._buffer.popleft())

        if spans:
            await self._transport.send_batch([self._span_to_dict(s) for s in spans])

    def _span_to_dict(self, span: SpanData) -> dict:
        return {
            "span_id": span.span_id,
            "trace_id": span.trace_id,
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
        self._buffer.append(span)
