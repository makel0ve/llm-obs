from types import SimpleNamespace

import pytest
import pytest_asyncio

import llm_obs
from llm_obs.integrations.anthropic import patch_anthropic
from llm_obs.integrations.openai import patch_openai


@pytest_asyncio.fixture(autouse=True)
async def reset_tracer():
    yield
    await llm_obs.shutdown(flush=False)


class FakeOpenAICompletions:
    def __init__(self, *, response=None, error: Exception | None = None):
        self.response = response
        self.error = error
        self.calls: list[tuple[tuple, dict]] = []

    async def create(self, *args, **kwargs):
        self.calls.append((args, kwargs))
        if self.error:
            raise self.error
        return self.response


class FakeOpenAIClient:
    def __init__(self, completions: FakeOpenAICompletions):
        self.chat = SimpleNamespace(completions=completions)


class FakeAnthropicMessages:
    def __init__(self, *, response=None, error: Exception | None = None):
        self.response = response
        self.error = error
        self.calls: list[tuple[tuple, dict]] = []

    async def create(self, *args, **kwargs):
        self.calls.append((args, kwargs))
        if self.error:
            raise self.error
        return self.response


class FakeAnthropicClient:
    def __init__(self, messages: FakeAnthropicMessages):
        self.messages = messages


class FakeAsyncStream:
    def __init__(self, events: list, *, error: Exception | None = None):
        self.events = events
        self.error = error
        self.closed = False

    async def __aiter__(self):
        for event in self.events:
            yield event
        if self.error:
            raise self.error

    async def aclose(self) -> None:
        self.closed = True


@pytest.mark.asyncio
async def test_openai_patch_records_success_usage_output_and_parent_span():
    tracer = llm_obs.init(api_key="test", endpoint="http://test")
    response = SimpleNamespace(
        choices=[
            SimpleNamespace(message=SimpleNamespace(content="openai response")),
        ],
        usage=SimpleNamespace(prompt_tokens=12, completion_tokens=7),
    )
    completions = FakeOpenAICompletions(response=response)
    client = patch_openai(FakeOpenAIClient(completions))

    @llm_obs.trace(name="parent")
    async def parent_call():
        return await client.chat.completions.create(
            model="gpt-4o-mini",
            messages=[{"role": "user", "content": "Hello"}],
        )

    result = await parent_call()

    assert result is response
    assert len(tracer._buffer) == 2
    provider_span, parent_span = tracer._buffer
    assert provider_span.name == "openai.chat.completions.create"
    assert provider_span.provider == "openai"
    assert provider_span.model == "gpt-4o-mini"
    assert provider_span.output == "openai response"
    assert provider_span.input_tokens == 12
    assert provider_span.output_tokens == 7
    assert provider_span.trace_id == parent_span.trace_id
    assert provider_span.parent_span_id == parent_span.span_id
    assert provider_span.error is None


@pytest.mark.asyncio
async def test_openai_double_patch_is_noop_for_success_and_nested_parent_span():
    tracer = llm_obs.init(api_key="test", endpoint="http://test")
    response = SimpleNamespace(
        choices=[
            SimpleNamespace(message=SimpleNamespace(content="openai response")),
        ],
        usage=SimpleNamespace(prompt_tokens=12, completion_tokens=7),
    )
    completions = FakeOpenAICompletions(response=response)
    client = FakeOpenAIClient(completions)
    first_create = patch_openai(client).chat.completions.create
    second_create = patch_openai(client).chat.completions.create

    assert second_create is first_create

    async with llm_obs.span("manual.parent") as manual_span:
        result = await client.chat.completions.create(
            model="gpt-4o-mini",
            messages=[{"role": "user", "content": "Hello"}],
        )
        manual_span.set_output(result.choices[0].message.content)

    assert result is response
    assert len(completions.calls) == 1
    assert len(tracer._buffer) == 2
    provider_span, parent_span = tracer._buffer
    assert provider_span.name == "openai.chat.completions.create"
    assert parent_span.name == "manual.parent"
    assert provider_span.trace_id == parent_span.trace_id
    assert provider_span.parent_span_id == parent_span.span_id


@pytest.mark.asyncio
async def test_openai_patch_records_exception():
    tracer = llm_obs.init(api_key="test", endpoint="http://test")
    client = patch_openai(
        FakeOpenAIClient(FakeOpenAICompletions(error=RuntimeError("openai down")))
    )

    with pytest.raises(RuntimeError, match="openai down"):
        await client.chat.completions.create(model="gpt-4o-mini", messages=[])

    assert len(tracer._buffer) == 1
    span = tracer._buffer[0]
    assert span.name == "openai.chat.completions.create"
    assert span.error == "openai down"
    assert span.input_tokens == 0
    assert span.output_tokens == 0
    assert span.output is None


@pytest.mark.asyncio
async def test_openai_double_patch_is_noop_for_exception():
    tracer = llm_obs.init(api_key="test", endpoint="http://test")
    completions = FakeOpenAICompletions(error=RuntimeError("openai down"))
    client = FakeOpenAIClient(completions)
    patch_openai(client)
    patch_openai(client)

    with pytest.raises(RuntimeError, match="openai down"):
        await client.chat.completions.create(model="gpt-4o-mini", messages=[])

    assert len(completions.calls) == 1
    assert len(tracer._buffer) == 1
    span = tracer._buffer[0]
    assert span.name == "openai.chat.completions.create"
    assert span.error == "openai down"


@pytest.mark.asyncio
async def test_openai_stream_records_after_full_consumption_and_parent_span():
    tracer = llm_obs.init(api_key="test", endpoint="http://test")
    stream = FakeAsyncStream(
        [
            SimpleNamespace(
                choices=[SimpleNamespace(delta=SimpleNamespace(content="Hello"))],
                usage=None,
            ),
            SimpleNamespace(
                choices=[SimpleNamespace(delta=SimpleNamespace(content=" world"))],
                usage=None,
            ),
            SimpleNamespace(
                choices=[],
                usage=SimpleNamespace(prompt_tokens=11, completion_tokens=5),
            ),
        ]
    )
    client = patch_openai(FakeOpenAIClient(FakeOpenAICompletions(response=stream)))
    chunks = []

    async with llm_obs.span("manual.parent") as manual_span:
        response_stream = await client.chat.completions.create(
            model="gpt-4o-mini",
            messages=[{"role": "user", "content": "Hello"}],
            stream=True,
            stream_options={"include_usage": True},
        )
        assert len(tracer._buffer) == 0
        async for chunk in response_stream:
            chunks.append(chunk)
        manual_span.set_output("parent done")

    assert chunks == stream.events
    assert len(tracer._buffer) == 2
    provider_span, parent_span = tracer._buffer
    assert provider_span.name == "openai.chat.completions.create"
    assert provider_span.output == "Hello world"
    assert provider_span.input_tokens == 11
    assert provider_span.output_tokens == 5
    assert provider_span.metadata == {"stream": True, "stream_complete": True}
    assert provider_span.trace_id == parent_span.trace_id
    assert provider_span.parent_span_id == parent_span.span_id


@pytest.mark.asyncio
async def test_openai_stream_records_error_and_partial_output():
    tracer = llm_obs.init(api_key="test", endpoint="http://test")
    stream = FakeAsyncStream(
        [
            SimpleNamespace(
                choices=[SimpleNamespace(delta=SimpleNamespace(content="partial"))],
                usage=None,
            )
        ],
        error=RuntimeError("stream failed"),
    )
    client = patch_openai(FakeOpenAIClient(FakeOpenAICompletions(response=stream)))

    response_stream = await client.chat.completions.create(
        model="gpt-4o-mini", messages=[], stream=True
    )
    with pytest.raises(RuntimeError, match="stream failed"):
        async for _chunk in response_stream:
            pass

    assert len(tracer._buffer) == 1
    span = tracer._buffer[0]
    assert span.output == "partial"
    assert span.error == "stream failed"
    assert span.metadata == {"stream": True, "stream_complete": False}


@pytest.mark.asyncio
async def test_openai_stream_records_early_cancellation():
    tracer = llm_obs.init(api_key="test", endpoint="http://test")
    stream = FakeAsyncStream(
        [
            SimpleNamespace(
                choices=[SimpleNamespace(delta=SimpleNamespace(content="first"))],
                usage=None,
            ),
            SimpleNamespace(
                choices=[SimpleNamespace(delta=SimpleNamespace(content=" second"))],
                usage=None,
            ),
        ]
    )
    client = patch_openai(FakeOpenAIClient(FakeOpenAICompletions(response=stream)))

    response_stream = await client.chat.completions.create(
        model="gpt-4o-mini", messages=[], stream=True
    )
    async for _chunk in response_stream:
        break
    await response_stream.aclose()

    assert stream.closed is True
    assert len(tracer._buffer) == 1
    span = tracer._buffer[0]
    assert span.output == "first"
    assert span.error is None
    assert span.metadata == {"stream": True, "stream_complete": False}


@pytest.mark.asyncio
async def test_openai_patch_records_parent_span_inside_manual_span():
    tracer = llm_obs.init(api_key="test", endpoint="http://test")
    response = SimpleNamespace(
        choices=[
            SimpleNamespace(message=SimpleNamespace(content="openai response")),
        ],
        usage=SimpleNamespace(prompt_tokens=8, completion_tokens=5),
    )
    completions = FakeOpenAICompletions(response=response)
    client = patch_openai(FakeOpenAIClient(completions))

    async with llm_obs.span("manual.parent") as manual_span:
        result = await client.chat.completions.create(
            model="gpt-4o-mini",
            messages=[{"role": "user", "content": "Hello"}],
        )
        manual_span.set_output(result.choices[0].message.content)

    assert result is response
    assert len(tracer._buffer) == 2
    provider_span, parent_span = tracer._buffer
    assert provider_span.name == "openai.chat.completions.create"
    assert parent_span.name == "manual.parent"
    assert provider_span.trace_id == parent_span.trace_id
    assert provider_span.parent_span_id == parent_span.span_id
    assert parent_span.parent_span_id is None


@pytest.mark.asyncio
async def test_anthropic_patch_records_success_usage_output_and_parent_span():
    tracer = llm_obs.init(api_key="test", endpoint="http://test")
    response = SimpleNamespace(
        content=[SimpleNamespace(text="anthropic response")],
        usage=SimpleNamespace(input_tokens=15, output_tokens=9),
    )
    messages = FakeAnthropicMessages(response=response)
    client = patch_anthropic(FakeAnthropicClient(messages))

    @llm_obs.trace(name="parent")
    async def parent_call():
        return await client.messages.create(
            model="claude-sonnet-4-6",
            system="You are concise.",
            messages=[{"role": "user", "content": "Hello"}],
        )

    result = await parent_call()

    assert result is response
    assert len(tracer._buffer) == 2
    provider_span, parent_span = tracer._buffer
    assert provider_span.name == "anthropic.messages.create"
    assert provider_span.provider == "anthropic"
    assert provider_span.model == "claude-sonnet-4-6"
    assert provider_span.output == "anthropic response"
    assert provider_span.input_tokens == 15
    assert provider_span.output_tokens == 9
    assert provider_span.trace_id == parent_span.trace_id
    assert provider_span.parent_span_id == parent_span.span_id
    assert provider_span.metadata["system"] == "You are concise."
    assert provider_span.error is None


@pytest.mark.asyncio
async def test_anthropic_double_patch_is_noop_for_success_and_nested_parent_span():
    tracer = llm_obs.init(api_key="test", endpoint="http://test")
    response = SimpleNamespace(
        content=[SimpleNamespace(text="anthropic response")],
        usage=SimpleNamespace(input_tokens=15, output_tokens=9),
    )
    messages = FakeAnthropicMessages(response=response)
    client = FakeAnthropicClient(messages)
    first_create = patch_anthropic(client).messages.create
    second_create = patch_anthropic(client).messages.create

    assert second_create is first_create

    async with llm_obs.span("manual.parent") as manual_span:
        result = await client.messages.create(
            model="claude-sonnet-4-6",
            system="You are concise.",
            messages=[{"role": "user", "content": "Hello"}],
        )
        manual_span.set_output(result.content[0].text)

    assert result is response
    assert len(messages.calls) == 1
    assert len(tracer._buffer) == 2
    provider_span, parent_span = tracer._buffer
    assert provider_span.name == "anthropic.messages.create"
    assert parent_span.name == "manual.parent"
    assert provider_span.trace_id == parent_span.trace_id
    assert provider_span.parent_span_id == parent_span.span_id
    assert provider_span.metadata["system"] == "You are concise."


@pytest.mark.asyncio
async def test_anthropic_patch_records_exception():
    tracer = llm_obs.init(api_key="test", endpoint="http://test")
    client = patch_anthropic(
        FakeAnthropicClient(FakeAnthropicMessages(error=RuntimeError("anthropic down")))
    )

    with pytest.raises(RuntimeError, match="anthropic down"):
        await client.messages.create(model="claude-sonnet-4-6", messages=[])

    assert len(tracer._buffer) == 1
    span = tracer._buffer[0]
    assert span.name == "anthropic.messages.create"
    assert span.error == "anthropic down"
    assert span.input_tokens == 0
    assert span.output_tokens == 0
    assert span.output is None


@pytest.mark.asyncio
async def test_anthropic_double_patch_is_noop_for_exception():
    tracer = llm_obs.init(api_key="test", endpoint="http://test")
    messages = FakeAnthropicMessages(error=RuntimeError("anthropic down"))
    client = FakeAnthropicClient(messages)
    patch_anthropic(client)
    patch_anthropic(client)

    with pytest.raises(RuntimeError, match="anthropic down"):
        await client.messages.create(model="claude-sonnet-4-6", messages=[])

    assert len(messages.calls) == 1
    assert len(tracer._buffer) == 1
    span = tracer._buffer[0]
    assert span.name == "anthropic.messages.create"
    assert span.error == "anthropic down"


@pytest.mark.asyncio
async def test_anthropic_stream_records_after_full_consumption_and_parent_span():
    tracer = llm_obs.init(api_key="test", endpoint="http://test")
    stream = FakeAsyncStream(
        [
            SimpleNamespace(
                type="message_start",
                message=SimpleNamespace(
                    usage=SimpleNamespace(input_tokens=13, output_tokens=0)
                ),
            ),
            SimpleNamespace(
                type="content_block_delta",
                delta=SimpleNamespace(text="Hello"),
            ),
            SimpleNamespace(
                type="content_block_delta",
                delta=SimpleNamespace(text=" Claude"),
            ),
            SimpleNamespace(
                type="message_delta",
                usage=SimpleNamespace(output_tokens=6),
            ),
        ]
    )
    client = patch_anthropic(
        FakeAnthropicClient(FakeAnthropicMessages(response=stream))
    )
    events = []

    async with llm_obs.span("manual.parent") as manual_span:
        response_stream = await client.messages.create(
            model="claude-sonnet-4-6",
            system="You are concise.",
            messages=[{"role": "user", "content": "Hello"}],
            stream=True,
        )
        assert len(tracer._buffer) == 0
        async for event in response_stream:
            events.append(event)
        manual_span.set_output("parent done")

    assert events == stream.events
    assert len(tracer._buffer) == 2
    provider_span, parent_span = tracer._buffer
    assert provider_span.name == "anthropic.messages.create"
    assert provider_span.output == "Hello Claude"
    assert provider_span.input_tokens == 13
    assert provider_span.output_tokens == 6
    assert provider_span.metadata == {
        "system": "You are concise.",
        "stream": True,
        "stream_complete": True,
    }
    assert provider_span.trace_id == parent_span.trace_id
    assert provider_span.parent_span_id == parent_span.span_id


@pytest.mark.asyncio
async def test_anthropic_stream_records_error_and_partial_output():
    tracer = llm_obs.init(api_key="test", endpoint="http://test")
    stream = FakeAsyncStream(
        [
            SimpleNamespace(
                type="content_block_delta",
                delta=SimpleNamespace(text="partial"),
            )
        ],
        error=RuntimeError("anthropic stream failed"),
    )
    client = patch_anthropic(
        FakeAnthropicClient(FakeAnthropicMessages(response=stream))
    )

    response_stream = await client.messages.create(
        model="claude-sonnet-4-6", messages=[], stream=True
    )
    with pytest.raises(RuntimeError, match="anthropic stream failed"):
        async for _event in response_stream:
            pass

    assert len(tracer._buffer) == 1
    span = tracer._buffer[0]
    assert span.output == "partial"
    assert span.error == "anthropic stream failed"
    assert span.metadata == {"system": None, "stream": True, "stream_complete": False}


@pytest.mark.asyncio
async def test_provider_extractors_accept_dict_like_responses():
    tracer = llm_obs.init(api_key="test", endpoint="http://test")
    openai_client = patch_openai(
        FakeOpenAIClient(
            FakeOpenAICompletions(
                response={
                    "choices": [{"message": {"content": "dict openai"}}],
                    "usage": {"prompt_tokens": 3, "completion_tokens": 4},
                }
            )
        )
    )
    anthropic_client = patch_anthropic(
        FakeAnthropicClient(
            FakeAnthropicMessages(
                response={
                    "content": [{"text": "dict anthropic"}],
                    "usage": {"input_tokens": 5, "output_tokens": 6},
                }
            )
        )
    )

    await openai_client.chat.completions.create(model="gpt-4o-mini", messages=[])
    await anthropic_client.messages.create(model="claude-sonnet-4-6", messages=[])

    assert [span.output for span in tracer._buffer] == [
        "dict openai",
        "dict anthropic",
    ]
    assert [(span.input_tokens, span.output_tokens) for span in tracer._buffer] == [
        (3, 4),
        (5, 6),
    ]
