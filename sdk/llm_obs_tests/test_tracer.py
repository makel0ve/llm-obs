import pytest
import httpx
import respx
import pytest_asyncio

import llm_obs
from llm_obs.tracer import LLMTracer, SpanData


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
    assert tracer._buffer[0].trace_id == tracer._buffer[1].trace_id


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
        assert len(tracer._buffer) == 0
