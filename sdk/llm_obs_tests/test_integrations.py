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
    assert provider_span.metadata["parent_span_id"] == parent_span.span_id
    assert provider_span.error is None


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
    assert provider_span.metadata["parent_span_id"] == parent_span.span_id
    assert provider_span.metadata["system"] == "You are concise."
    assert provider_span.error is None


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
