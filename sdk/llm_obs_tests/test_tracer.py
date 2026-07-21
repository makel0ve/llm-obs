import asyncio
import json

import pytest
import httpx
import respx
import pytest_asyncio

import llm_obs
from llm_obs.tracer import FlushBatch, LLMTracer, SpanData
from llm_obs.transport import HttpTransport


@pytest_asyncio.fixture(autouse=True)
async def reset_tracer():
    yield
    await llm_obs.shutdown(flush=False)


@pytest.mark.asyncio
async def test_double_init_raises():
    llm_obs.init(api_key="k", endpoint="http://test")
    with pytest.raises(RuntimeError, match="already initialized"):
        llm_obs.init(api_key="k2", endpoint="http://test")


@pytest.mark.asyncio
async def test_shutdown_allows_reinitialization():
    first = llm_obs.init(api_key="k", endpoint="http://test")
    assert llm_obs.get_tracer() is first

    await llm_obs.shutdown(flush=False)
    assert llm_obs.get_tracer() is None

    second = llm_obs.init(api_key="k2", endpoint="http://test")
    assert second is not first
    assert llm_obs.get_tracer() is second


def test_init_without_running_loop_does_not_schedule_background_start(monkeypatch):
    loop = asyncio.new_event_loop()
    scheduled = False

    def fail_if_scheduled(_coro):
        nonlocal scheduled
        scheduled = True
        raise AssertionError("start should not be scheduled on a non-running loop")

    monkeypatch.setattr("llm_obs.asyncio.ensure_future", fail_if_scheduled)
    asyncio.set_event_loop(loop)
    try:
        tracer = llm_obs.init(api_key="k", endpoint="http://test")
    finally:
        asyncio.set_event_loop(None)
        loop.close()

    assert tracer._flush_task is None
    assert scheduled is False


@pytest.mark.asyncio
async def test_init_schedules_background_start_on_running_loop():
    tracer = llm_obs.init(api_key="k", endpoint="http://test")

    await asyncio.sleep(0)

    assert tracer._flush_task is not None
    assert not tracer._flush_task.done()


@pytest.mark.asyncio
async def test_repeated_start_reuses_existing_flush_loop():
    tracer = LLMTracer(api_key="k", endpoint="http://test")

    await tracer.start()
    first_task = tracer._flush_task
    await tracer.start()

    assert first_task is not None
    assert tracer._flush_task is first_task
    assert not first_task.done()

    await tracer.shutdown(flush=False)


@pytest.mark.asyncio
async def test_shutdown_without_start_is_idempotent():
    tracer = LLMTracer(api_key="k", endpoint="http://test")

    await tracer.shutdown(flush=False)
    await tracer.shutdown(flush=False)

    assert tracer._closed is True
    assert tracer._flush_task is None


def test_tracer_start_shutdown_inside_asyncio_run():
    async def main() -> None:
        tracer = LLMTracer(api_key="k", endpoint="http://test")
        await tracer.start()
        assert tracer._flush_task is not None
        await tracer.shutdown(flush=False)
        assert tracer._closed is True

    asyncio.run(main())


@pytest.mark.asyncio
async def test_trace_decorator_records_span():
    tracer = llm_obs.init(api_key="test", endpoint="http://test")

    @llm_obs.trace(name="test_func")
    async def my_func():
        return "ok"

    result = await my_func()
    assert result == "ok"
    assert len(tracer._buffer) == 1
    assert tracer._buffer[0].name == "test_func"
    assert tracer._buffer[0].error is None


@pytest.mark.asyncio
async def test_trace_records_error():
    tracer = llm_obs.init(api_key="test", endpoint="http://test")

    @llm_obs.trace()
    async def failing():
        raise ValueError("test error")

    with pytest.raises(ValueError):
        await failing()

    assert tracer._buffer[0].error is not None
    assert "ValueError" in tracer._buffer[0].error


@pytest.mark.asyncio
async def test_manual_span_records_success_fields():
    tracer = llm_obs.init(api_key="test", endpoint="http://test")

    async with llm_obs.span(
        "manual.llm_call",
        provider="openai",
        model="gpt-4o-mini",
        input_messages=[{"role": "user", "content": "Hello"}],
        metadata={"source": "test"},
    ) as span:
        span.set_output("manual response")
        span.set_tokens(input_tokens=11, output_tokens=7)
        span.update_metadata({"route": "chat"})

    assert len(tracer._buffer) == 1
    recorded = tracer._buffer[0]
    assert recorded.name == "manual.llm_call"
    assert recorded.provider == "openai"
    assert recorded.model == "gpt-4o-mini"
    assert recorded.input_messages == [{"role": "user", "content": "Hello"}]
    assert recorded.output == "manual response"
    assert recorded.input_tokens == 11
    assert recorded.output_tokens == 7
    assert recorded.metadata == {"source": "test", "route": "chat"}
    assert recorded.parent_span_id is None
    assert recorded.error is None
    assert recorded.latency_ms >= 0


@pytest.mark.asyncio
async def test_manual_span_records_error_and_reraises():
    tracer = llm_obs.init(api_key="test", endpoint="http://test")

    with pytest.raises(ValueError, match="manual error"):
        async with llm_obs.span("manual.failure"):
            raise ValueError("manual error")

    assert len(tracer._buffer) == 1
    recorded = tracer._buffer[0]
    assert recorded.name == "manual.failure"
    assert recorded.error is not None
    assert "ValueError: manual error" in recorded.error


@pytest.mark.asyncio
async def test_nested_traces_share_trace_id():
    tracer = llm_obs.init(api_key="test", endpoint="http://test")

    @llm_obs.trace()
    async def inner():
        pass

    @llm_obs.trace()
    async def outer():
        await inner()

    await outer()
    assert len(tracer._buffer) == 2
    inner_span, outer_span = tracer._buffer
    assert inner_span.trace_id == outer_span.trace_id
    assert inner_span.parent_span_id == outer_span.span_id
    assert outer_span.parent_span_id is None


@pytest.mark.asyncio
async def test_buffer_overflow_drops_oldest():
    tracer = LLMTracer(api_key="k", endpoint="http://test", buffer_size=3)

    for i in range(10):
        tracer.record(
            SpanData(
                trace_id=f"t{i}",
                span_id=f"s{i}",
                name=f"span_{i}",
                provider="openai",
                model="gpt-4o",
                input_messages=[],
                latency_ms=10,
            )
        )

    assert len(tracer._buffer) == 3
    assert tracer._buffer[-1].name == "span_9"
    diagnostics = tracer.sdk_diagnostics
    assert diagnostics.dropped_spans == 7
    assert diagnostics.last_drop_reason == "buffer_overflow"
    assert diagnostics.buffered_spans == 3
    assert diagnostics.active_buffered_spans == 3
    assert diagnostics.pending_spans == 0
    assert diagnostics.pending_batches == 0
    assert diagnostics.buffer_size == 3
    diagnostics_text = repr(diagnostics.__dict__)
    assert "input_messages" not in diagnostics_text
    assert "X-API-Key" not in diagnostics_text


@pytest.mark.asyncio
async def test_flush_sends_http():
    tracer = llm_obs.init(api_key="test", endpoint="http://server")

    with respx.mock:
        route = respx.post("http://server/v1/ingest").mock(
            return_value=httpx.Response(202, json={"batch_id": "b1"})
        )

        tracer.record(
            SpanData(
                trace_id="t1",
                span_id="s1",
                name="test",
                provider="openai",
                model="gpt-4o",
                input_messages=[],
                latency_ms=100,
            )
        )

        await tracer._flush()
        assert route.called
        payload = json.loads(route.calls.last.request.content)
        assert payload["spans"][0]["parent_span_id"] is None
        assert len(tracer._buffer) == 0


@pytest.mark.asyncio
async def test_flush_sends_parent_span_id():
    tracer = llm_obs.init(api_key="test", endpoint="http://server")

    with respx.mock:
        route = respx.post("http://server/v1/ingest").mock(
            return_value=httpx.Response(202, json={"batch_id": "b1"})
        )

        tracer.record(
            SpanData(
                trace_id="t1",
                span_id="child",
                parent_span_id="parent",
                name="test",
                provider="openai",
                model="gpt-4o",
                input_messages=[],
                latency_ms=100,
            )
        )

        await tracer._flush()
        payload = json.loads(route.calls.last.request.content)
        assert payload["spans"][0]["parent_span_id"] == "parent"


def make_span(name: str = "test") -> SpanData:
    return SpanData(
        trace_id="t1",
        span_id="s1",
        name=name,
        provider="openai",
        model="gpt-4o",
        input_messages=[],
        latency_ms=100,
    )


async def no_sleep(_delay: float) -> None:
    return None


def disable_transport_backoff(
    monkeypatch: pytest.MonkeyPatch, transport: HttpTransport
) -> None:
    monkeypatch.setattr("llm_obs.transport.asyncio.sleep", no_sleep)
    monkeypatch.setattr(transport, "_jitter", lambda _attempt: 0)


@pytest.mark.asyncio
async def test_shutdown_flush_true_sends_buffer():
    tracer = llm_obs.init(api_key="test", endpoint="http://server")

    with respx.mock:
        route = respx.post("http://server/v1/ingest").mock(
            return_value=httpx.Response(202, json={"batch_id": "b1"})
        )

        tracer.record(make_span())
        await llm_obs.shutdown()

        assert route.called
        assert len(tracer._buffer) == 0
        assert llm_obs.get_tracer() is None


@pytest.mark.asyncio
async def test_shutdown_flush_false_discards_buffer_without_http():
    tracer = llm_obs.init(api_key="test", endpoint="http://server")

    with respx.mock:
        route = respx.post("http://server/v1/ingest").mock(
            return_value=httpx.Response(202, json={"batch_id": "b1"})
        )

        tracer.record(make_span())
        await llm_obs.shutdown(flush=False)

        assert not route.called
        assert len(tracer._buffer) == 0


@pytest.mark.asyncio
async def test_shutdown_flush_failure_keeps_safe_diagnostics(monkeypatch):
    tracer = llm_obs.init(api_key="test", endpoint="http://server")

    disable_transport_backoff(monkeypatch, tracer._transport)

    with respx.mock:
        respx.post("http://server/v1/ingest").mock(
            side_effect=[
                httpx.Response(500),
                httpx.Response(502),
                httpx.Response(503),
            ]
        )

        tracer.record(make_span())
        await llm_obs.shutdown()

    transport_diagnostics = llm_obs.get_diagnostics()
    assert transport_diagnostics is not None
    assert transport_diagnostics.ok is False
    assert transport_diagnostics.reason == "http_error"
    assert transport_diagnostics.status_code == 503

    sdk_diagnostics = llm_obs.get_sdk_diagnostics()
    assert sdk_diagnostics is not None
    assert sdk_diagnostics.failed_flushes == 1
    assert sdk_diagnostics.final_delivery_failures == 1
    assert sdk_diagnostics.buffered_spans == 1
    assert sdk_diagnostics.active_buffered_spans == 0
    assert sdk_diagnostics.pending_spans == 1
    assert sdk_diagnostics.pending_batches == 1
    assert sdk_diagnostics.last_flush_reason == "http_error"


@pytest.mark.asyncio
async def test_failed_flush_keeps_buffered_spans():
    tracer = llm_obs.init(api_key="test", endpoint="http://server")

    with respx.mock:
        respx.post("http://server/v1/ingest").mock(
            return_value=httpx.Response(429, headers={"Retry-After": "5"})
        )

        tracer.record(make_span())
        sent = await tracer._flush()

        assert sent is False
        assert len(tracer._buffer) == 0
        assert len(tracer._pending_batches) == 1
        assert tracer._pending_batches[0].spans[0].name == "test"
        assert tracer.sdk_diagnostics.buffered_spans == 1
        assert tracer.sdk_diagnostics.active_buffered_spans == 0
        assert tracer.sdk_diagnostics.pending_spans == 1
        assert tracer.sdk_diagnostics.pending_batches == 1
        diagnostics = llm_obs.get_diagnostics()
        assert diagnostics is not None
        assert diagnostics.ok is False
        assert diagnostics.reason == "rate_limited"
        assert diagnostics.spans_count == 1
        assert diagnostics.attempts == 1
        assert diagnostics.status_code == 429
        assert diagnostics.retry_after == 5
        diagnostics_text = repr(diagnostics.__dict__)
        assert "X-API-Key" not in diagnostics_text
        assert "gpt-4o" not in diagnostics_text
        assert "input_messages" not in diagnostics_text


@pytest.mark.asyncio
async def test_get_sdk_diagnostics_reports_drop_and_buffer_metrics():
    tracer = llm_obs.init(api_key="test", endpoint="http://test", buffer_size=2)

    tracer.record(make_span("first"))
    tracer.record(make_span("second"))
    tracer.record(make_span("third"))

    diagnostics = llm_obs.get_sdk_diagnostics()

    assert diagnostics is not None
    assert diagnostics.dropped_spans == 1
    assert diagnostics.last_drop_reason == "buffer_overflow"
    assert diagnostics.buffered_spans == 2
    assert diagnostics.active_buffered_spans == 2
    assert diagnostics.pending_spans == 0
    assert diagnostics.pending_batches == 0
    assert diagnostics.failed_flushes == 0
    assert diagnostics.final_delivery_failures == 0
    assert diagnostics.buffer_size == 2


def test_sync_flush_on_exit_flushes_buffer(monkeypatch):
    tracer = LLMTracer(api_key="test", endpoint="http://server")
    flushed = False

    async def fake_flush():
        nonlocal flushed
        flushed = True
        tracer._buffer.clear()
        return True

    monkeypatch.setattr(tracer, "_flush", fake_flush)
    tracer.record(make_span())

    tracer._sync_flush_on_exit()

    assert flushed
    assert len(tracer._buffer) == 0


def test_sync_flush_on_exit_flushes_pending_before_active(monkeypatch):
    tracer = LLMTracer(api_key="test", endpoint="http://server")
    sent_batches: list[list[str]] = []

    async def send_batch(
        spans: list[dict], *, idempotency_key: str | None = None
    ) -> bool:
        sent_batches.append([span["name"] for span in spans])
        return True

    monkeypatch.setattr(tracer._transport, "send_batch", send_batch)
    tracer._pending_batches.append(
        FlushBatch(spans=[make_span("old")], idempotency_key="old-key")
    )
    tracer._pending_spans = 1
    tracer.record(make_span("new"))

    tracer._sync_flush_on_exit()

    assert sent_batches == [["old"], ["new"]]
    assert tracer.sdk_diagnostics.buffered_spans == 0


@pytest.mark.asyncio
async def test_transport_retries_5xx_then_succeeds(monkeypatch):
    transport = HttpTransport(endpoint="http://server", api_key="test")

    disable_transport_backoff(monkeypatch, transport)

    with respx.mock:
        route = respx.post("http://server/v1/ingest").mock(
            side_effect=[
                httpx.Response(500),
                httpx.Response(502),
                httpx.Response(202),
            ]
        )

        sent = await transport.send_batch(
            [{"span_id": "s1"}], idempotency_key="batch-key"
        )

    await transport.aclose()

    assert sent is True
    assert route.call_count == 3
    assert transport.last_diagnostics is not None
    assert transport.last_diagnostics.ok is True
    assert transport.last_diagnostics.reason == "sent"
    assert transport.last_diagnostics.attempts == 3
    assert transport.last_diagnostics.spans_count == 1
    assert [
        json.loads(call.request.content)["idempotency_key"] for call in route.calls
    ] == ["batch-key", "batch-key", "batch-key"]


@pytest.mark.asyncio
async def test_transport_records_final_http_failure_after_retries(monkeypatch):
    transport = HttpTransport(endpoint="http://server", api_key="test")

    disable_transport_backoff(monkeypatch, transport)

    with respx.mock:
        route = respx.post("http://server/v1/ingest").mock(
            side_effect=[
                httpx.Response(500),
                httpx.Response(502),
                httpx.Response(503),
            ]
        )

        sent = await transport.send_batch(
            [{"span_id": "s1"}], idempotency_key="timeout-key"
        )

    await transport.aclose()

    assert sent is False
    assert route.call_count == 3
    assert transport.last_diagnostics is not None
    assert transport.last_diagnostics.ok is False
    assert transport.last_diagnostics.reason == "http_error"
    assert transport.last_diagnostics.status_code == 503
    assert transport.last_diagnostics.attempts == 3


@pytest.mark.asyncio
async def test_transport_records_final_timeout_after_retries(monkeypatch):
    transport = HttpTransport(endpoint="http://server", api_key="test")
    disable_transport_backoff(monkeypatch, transport)

    with respx.mock:
        route = respx.post("http://server/v1/ingest").mock(
            side_effect=httpx.ReadTimeout("server accepted request but timed out")
        )

        sent = await transport.send_batch(
            [{"span_id": "s1"}], idempotency_key="timeout-key"
        )

    await transport.aclose()

    assert sent is False
    assert route.call_count == 3
    assert transport.last_diagnostics is not None
    assert transport.last_diagnostics.ok is False
    assert transport.last_diagnostics.reason == "connection_error"
    assert transport.last_diagnostics.error_type == "ReadTimeout"
    assert transport.last_diagnostics.attempts == 3
    assert transport.last_diagnostics.spans_count == 1
    assert [
        json.loads(call.request.content)["idempotency_key"] for call in route.calls
    ] == ["timeout-key", "timeout-key", "timeout-key"]


@pytest.mark.asyncio
async def test_transport_records_final_connection_reset_after_retries(monkeypatch):
    transport = HttpTransport(endpoint="http://server", api_key="test")
    disable_transport_backoff(monkeypatch, transport)

    with respx.mock:
        route = respx.post("http://server/v1/ingest").mock(
            side_effect=httpx.ConnectError("connection reset by peer")
        )

        sent = await transport.send_batch([{"span_id": "s1"}])

    await transport.aclose()

    assert sent is False
    assert route.call_count == 3
    assert transport.last_diagnostics is not None
    assert transport.last_diagnostics.ok is False
    assert transport.last_diagnostics.reason == "connection_error"
    assert transport.last_diagnostics.error_type == "ConnectError"
    assert transport.last_diagnostics.attempts == 3
    assert transport.last_diagnostics.spans_count == 1


@pytest.mark.asyncio
async def test_failed_long_flush_preserves_new_spans_and_retries_failed_batch_first(
    monkeypatch,
):
    tracer = LLMTracer(api_key="test", endpoint="http://server", buffer_size=3)
    started = asyncio.Event()
    release = asyncio.Event()
    sent_batches: list[list[str]] = []
    sent_idempotency_keys: list[str | None] = []
    generated_keys = iter(["old-key", "new-key"])
    monkeypatch.setattr("llm_obs.tracer.uuid.uuid4", lambda: next(generated_keys))

    async def fail_first_batch_after_release(
        spans: list[dict], *, idempotency_key: str | None = None
    ) -> bool:
        sent_batches.append([span["name"] for span in spans])
        sent_idempotency_keys.append(idempotency_key)
        if len(sent_batches) == 1:
            started.set()
            await release.wait()
            return False
        return True

    monkeypatch.setattr(tracer._transport, "send_batch", fail_first_batch_after_release)

    for name in ("old_1", "old_2", "old_3"):
        tracer.record(make_span(name))

    flush_task = asyncio.create_task(tracer._flush())
    await started.wait()

    assert len(tracer._buffer) == 0

    for name in ("new_1", "new_2", "new_3"):
        tracer.record(make_span(name))

    assert [span.name for span in tracer._buffer] == ["new_1", "new_2", "new_3"]
    assert tracer.sdk_diagnostics.dropped_spans == 0

    release.set()
    sent = await flush_task

    assert sent is False
    assert [span.name for span in tracer._pending_batches[0].spans] == [
        "old_1",
        "old_2",
        "old_3",
    ]
    assert [span.name for span in tracer._buffer] == ["new_1", "new_2", "new_3"]
    assert tracer.sdk_diagnostics.failed_flushes == 1
    assert tracer.sdk_diagnostics.dropped_spans == 0
    assert tracer.sdk_diagnostics.buffered_spans == 6
    assert tracer.sdk_diagnostics.active_buffered_spans == 3
    assert tracer.sdk_diagnostics.pending_spans == 3
    assert tracer.sdk_diagnostics.pending_batches == 1

    assert await tracer._flush() is True
    assert [span.name for span in tracer._buffer] == ["new_1", "new_2", "new_3"]
    assert tracer.sdk_diagnostics.active_buffered_spans == 3
    assert tracer.sdk_diagnostics.pending_spans == 0
    assert tracer.sdk_diagnostics.pending_batches == 0

    assert await tracer._flush() is True
    assert len(tracer._buffer) == 0
    assert len(tracer._pending_batches) == 0
    assert tracer.sdk_diagnostics.buffered_spans == 0
    assert tracer.sdk_diagnostics.active_buffered_spans == 0
    assert tracer.sdk_diagnostics.pending_spans == 0
    assert tracer.sdk_diagnostics.pending_batches == 0
    assert sent_batches == [
        ["old_1", "old_2", "old_3"],
        ["old_1", "old_2", "old_3"],
        ["new_1", "new_2", "new_3"],
    ]
    assert sent_idempotency_keys == ["old-key", "old-key", "new-key"]


@pytest.mark.asyncio
async def test_tracer_generates_new_idempotency_key_per_active_batch(monkeypatch):
    tracer = LLMTracer(api_key="test", endpoint="http://server")
    generated_keys = iter(["first-key", "second-key"])
    sent_idempotency_keys: list[str | None] = []

    monkeypatch.setattr("llm_obs.tracer.uuid.uuid4", lambda: next(generated_keys))

    async def send_batch(
        _spans: list[dict], *, idempotency_key: str | None = None
    ) -> bool:
        sent_idempotency_keys.append(idempotency_key)
        return True

    monkeypatch.setattr(tracer._transport, "send_batch", send_batch)

    tracer.record(make_span("first"))
    assert await tracer._flush() is True

    tracer.record(make_span("second"))
    assert await tracer._flush() is True

    assert sent_idempotency_keys == ["first-key", "second-key"]


@pytest.mark.asyncio
async def test_transport_429_does_not_retry():
    transport = HttpTransport(endpoint="http://server", api_key="test")

    with respx.mock:
        route = respx.post("http://server/v1/ingest").mock(
            return_value=httpx.Response(429, headers={"Retry-After": "5"})
        )

        sent = await transport.send_batch([{"span_id": "s1"}])

    await transport.aclose()

    assert sent is False
    assert route.call_count == 1
    assert transport.last_diagnostics is not None
    assert transport.last_diagnostics.reason == "rate_limited"
    assert transport.last_diagnostics.retry_after == 5


def test_init_debug_can_be_enabled_by_argument():
    tracer = llm_obs.init(api_key="test", endpoint="http://test", debug=True)

    assert tracer._transport._debug is True


def test_env_debug_enables_auto_initialized_tracer(monkeypatch):
    monkeypatch.setenv("LLM_OBS_API_KEY", "test")
    monkeypatch.setenv("LLM_OBS_DEBUG", "1")

    tracer = llm_obs._get_or_create_tracer()

    assert tracer is not None
    assert tracer._transport._debug is True
