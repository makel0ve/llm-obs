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
```

Get the API key from the dashboard after account creation, or rotate it in
Project Settings. API keys are shown once.

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
buffered spans are flushed before Python exits. Use
`await llm_obs.shutdown(flush=False)` when a test should discard buffered spans.

## OpenAI async patching

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
