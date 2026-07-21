# LLM Obs Python SDK

Async Python SDK for sending LLM spans to an LLM Obs deployment.

## Install

Published package:

```bash
pip install llm-obs-sdk
```

Local development from this repository:

```bash
cd sdk
pip install -e .
```

## Environment

The SDK auto-initializes from environment variables when a traced function or
patched provider call runs.

```bash
export LLM_OBS_API_KEY=llmobs_your_key_here
export LLM_OBS_ENDPOINT=http://localhost:8000
# Optional: emit safe SDK delivery diagnostics.
export LLM_OBS_DEBUG=1
```

Get the API key from the dashboard after account creation, or rotate it in
Project Settings. API keys are shown once.

`LLM_OBS_DEBUG=1` enables extra SDK delivery diagnostics. Debug events and
diagnostic objects do not include API keys, prompts, outputs or span payloads.
They only include delivery metadata such as status code, retry count, retry
delay, span count and failure reason.

## Basic async trace

```python
import asyncio
import llm_obs


@llm_obs.trace(name="demo.llm_call", metadata={"source": "sdk-readme"})
async def call_llm(prompt: str) -> str:
    await asyncio.sleep(0.05)
    return f"demo response for: {prompt}"


async def main() -> None:
    response = await call_llm("Hello")
    print(response)
    await llm_obs.shutdown()


if __name__ == "__main__":
    asyncio.run(main())
```

Call `await llm_obs.shutdown()` in short-lived scripts, CLIs and tests so
buffered spans are flushed before Python exits. The default
`shutdown(flush=True)` attempts to send the current buffer before closing the
HTTP client. Use `await llm_obs.shutdown(flush=False)` when a test should
discard buffered spans.

## Manual async spans

Use `llm_obs.span` when a decorator is not a good fit, for example around a
dynamic workflow step or a provider call hidden behind another abstraction.

```python
import asyncio
import llm_obs


async def call_llm(prompt: str) -> str:
    async with llm_obs.span(
        "demo.manual_llm_call",
        provider="custom",
        model="demo-model",
        input_messages=[{"role": "user", "content": prompt}],
        metadata={"source": "manual-span"},
    ) as span:
        await asyncio.sleep(0.05)
        response = f"demo response for: {prompt}"
        span.set_output(response)
        span.set_tokens(input_tokens=12, output_tokens=7)
        return response


async def main() -> None:
    response = await call_llm("Hello")
    print(response)
    await llm_obs.shutdown()


if __name__ == "__main__":
    asyncio.run(main())
```

Manual spans preserve the same trace context as `@llm_obs.trace`, so patched
provider calls inside the context are recorded as child spans. If the context
raises an exception, the span is still recorded with the error and the exception
is re-raised.

## OpenAI async patching

The OpenAI package is optional. Install and create your async client in the
application, then pass it to `patch_openai`.

```python
import asyncio
import llm_obs
import openai
from llm_obs.integrations.openai import patch_openai


async def main() -> None:
    client = openai.AsyncOpenAI(api_key="...")
    client = patch_openai(client)

    response = await client.chat.completions.create(
        model="gpt-4o-mini",
        messages=[{"role": "user", "content": "Hello"}],
    )
    print(response.choices[0].message.content)
    await llm_obs.shutdown()


if __name__ == "__main__":
    asyncio.run(main())
```

## Anthropic async patching

The Anthropic package is optional. Install and create your async client in the
application, then pass it to `patch_anthropic`.

```python
import asyncio
import anthropic
import llm_obs
from llm_obs.integrations.anthropic import patch_anthropic


async def main() -> None:
    client = anthropic.AsyncAnthropic(api_key="...")
    client = patch_anthropic(client)

    response = await client.messages.create(
        model="claude-sonnet-4-6",
        max_tokens=128,
        messages=[{"role": "user", "content": "Hello"}],
    )
    print(response.content[0].text)
    await llm_obs.shutdown()


if __name__ == "__main__":
    asyncio.run(main())
```

## Smoke example

Run the safe demo span sender from the repository root:

```bash
export LLM_OBS_API_KEY=llmobs_your_key_here
export LLM_OBS_ENDPOINT=http://localhost:8000
python examples/sdk_smoke_demo.py
```

It does not call an external LLM provider. It only records one demo span and
flushes it to your local LLM Obs ingest API.

## Troubleshooting

### No spans appear

- Confirm `LLM_OBS_API_KEY` is set in the process that runs your app.
- Confirm `LLM_OBS_ENDPOINT` points to the API service, for example
  `http://localhost:8000`.
- For scripts and CLIs, call `await llm_obs.shutdown()` before exit.
- Check the dashboard time range. Recent demo spans may be outside a narrow
  filter.

### Auth failed

- API keys are project ingest keys, not login JWT tokens.
- If a key was exposed or lost, rotate it in Project Settings and update your
  environment.

### Endpoint wrong

- From a host process, use `http://localhost:8000`.
- From another Docker service in the compose network, use the backend service
  URL, for example `http://backend:8000`.

### Process exits before flush

The SDK buffers spans and flushes in the background. Short-lived processes should
end with:

```python
await llm_obs.shutdown()
```

If ingest returns a retryable server error, the transport retries before giving
up. If ingest returns `429 Too Many Requests` or the final retry fails, unsent
spans stay in the in-memory buffer for the lifetime of that tracer instead of
being marked as successfully flushed. Each SDK flush batch gets an automatic
`idempotency_key`; transport retries and later retry attempts for the same failed
batch reuse that key.

### Debug delivery diagnostics

Enable debug mode with an environment variable:

```bash
export LLM_OBS_DEBUG=1
```

Or pass it explicitly when initializing:

```python
llm_obs.init(
    api_key="llmobs_your_key_here",
    endpoint="http://localhost:8000",
    debug=True,
)
```

After a flush attempt, inspect the last safe delivery diagnostic:

```python
diagnostics = llm_obs.get_diagnostics()
if diagnostics and not diagnostics.ok:
    print(diagnostics.reason, diagnostics.status_code, diagnostics.attempts)
```

Inspect SDK-level counters for local drops and shutdown delivery failures:

```python
sdk_diagnostics = llm_obs.get_sdk_diagnostics()
if sdk_diagnostics:
    print(
        sdk_diagnostics.dropped_spans,
        sdk_diagnostics.final_delivery_failures,
        sdk_diagnostics.buffered_spans,
    )
```

These diagnostics are safe delivery metadata only. They do not include prompts,
outputs, span payloads or API keys.

Common failure reasons:

- `rate_limited`: ingest returned `429`; check `retry_after` and reduce send
  rate.
- `http_error`: ingest returned a non-retryable HTTP error, or the final retry
  still failed.
- `connection_error`: the SDK could not connect to the endpoint, or the request
  timed out after retries.
- `unknown_failure`: the transport exited without a more specific result.
- `buffer_overflow`: the in-memory span buffer was full and the oldest span was
  dropped before recording a new span.
