import json

import pytest
import httpx
import respx
import pytest_asyncio

import llm_obs
from llm_obs.tracer import LLMTracer, SpanData
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
async def test_failed_flush_keeps_buffered_spans():
    tracer = llm_obs.init(api_key="test", endpoint="http://server")

    with respx.mock:
        respx.post("http://server/v1/ingest").mock(
            return_value=httpx.Response(429, headers={"Retry-After": "5"})
        )

        tracer.record(make_span())
        sent = await tracer._flush()

        assert sent is False
        assert len(tracer._buffer) == 1
        assert tracer._buffer[0].name == "test"
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


@pytest.mark.asyncio
async def test_transport_retries_5xx_then_succeeds(monkeypatch):
    transport = HttpTransport(endpoint="http://server", api_key="test")

    async def no_sleep(_delay):
        return None

    monkeypatch.setattr("llm_obs.transport.asyncio.sleep", no_sleep)
    monkeypatch.setattr(transport, "_jitter", lambda _attempt: 0)

    with respx.mock:
        route = respx.post("http://server/v1/ingest").mock(
            side_effect=[
                httpx.Response(500),
                httpx.Response(502),
                httpx.Response(202),
            ]
        )

        sent = await transport.send_batch([{"span_id": "s1"}])

    await transport.aclose()

    assert sent is True
    assert route.call_count == 3
    assert transport.last_diagnostics is not None
    assert transport.last_diagnostics.ok is True
    assert transport.last_diagnostics.reason == "sent"
    assert transport.last_diagnostics.attempts == 3
    assert transport.last_diagnostics.spans_count == 1


@pytest.mark.asyncio
async def test_transport_records_final_http_failure_after_retries(monkeypatch):
    transport = HttpTransport(endpoint="http://server", api_key="test")

    async def no_sleep(_delay):
        return None

    monkeypatch.setattr("llm_obs.transport.asyncio.sleep", no_sleep)
    monkeypatch.setattr(transport, "_jitter", lambda _attempt: 0)

    with respx.mock:
        route = respx.post("http://server/v1/ingest").mock(
            side_effect=[
                httpx.Response(500),
                httpx.Response(502),
                httpx.Response(503),
            ]
        )

        sent = await transport.send_batch([{"span_id": "s1"}])

    await transport.aclose()

    assert sent is False
    assert route.call_count == 3
    assert transport.last_diagnostics is not None
    assert transport.last_diagnostics.ok is False
    assert transport.last_diagnostics.reason == "http_error"
    assert transport.last_diagnostics.status_code == 503
    assert transport.last_diagnostics.attempts == 3


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
