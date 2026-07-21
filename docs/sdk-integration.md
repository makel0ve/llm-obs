# SDK Integration Guide

This guide shows the shortest path from an API key to a visible trace in the
dashboard.

## Prerequisites

- LLM Obs backend is reachable from the application.
- You have a project API key from registration, Project Settings, or a managed
  ingest/read-write key.
- For short-lived scripts, the code can call `await llm_obs.shutdown()` before
  process exit.

## Install

Published package:

```bash
pip install llm-obs-sdk
```

Local repository checkout:

```bash
cd sdk
pip install -e .
```

## Environment

Host process:

```bash
export LLM_OBS_API_KEY=llmobs_your_key_here
export LLM_OBS_ENDPOINT=http://localhost:8000
```

Another service in the local Docker Compose network:

```bash
export LLM_OBS_API_KEY=llmobs_your_key_here
export LLM_OBS_ENDPOINT=http://backend:8000
```

## First Trace

From the repository root:

```bash
python examples/sdk_smoke_demo.py
```

Expected output:

```text
Sent demo span to http://localhost:8000
demo response for: Hello from the SDK smoke example
```

Then open the dashboard and check Overview or Traces with the `1h` or `24h`
range selected.

## Decorator Usage

```python
import asyncio
import llm_obs


@llm_obs.trace(name="demo.llm_call", metadata={"source": "readme"})
async def call_llm(prompt: str) -> str:
    await asyncio.sleep(0.05)
    return f"demo response for: {prompt}"


async def main() -> None:
    await call_llm("Hello")
    await llm_obs.shutdown()


asyncio.run(main())
```

## OpenAI Async Patching

```python
import asyncio
import llm_obs
import openai
from llm_obs.integrations.openai import patch_openai


async def main() -> None:
    client = patch_openai(openai.AsyncOpenAI(api_key="..."))
    response = await client.chat.completions.create(
        model="gpt-4o-mini",
        messages=[{"role": "user", "content": "Hello"}],
    )
    print(response.choices[0].message.content)
    await llm_obs.shutdown()


asyncio.run(main())
```

## Anthropic Async Patching

```python
import asyncio
import anthropic
import llm_obs
from llm_obs.integrations.anthropic import patch_anthropic


async def main() -> None:
    client = patch_anthropic(anthropic.AsyncAnthropic(api_key="..."))
    response = await client.messages.create(
        model="claude-sonnet-4-5",
        max_tokens=128,
        messages=[{"role": "user", "content": "Hello"}],
    )
    print(response.content[0].text)
    await llm_obs.shutdown()


asyncio.run(main())
```

## Streaming Async Patching

Patched OpenAI and Anthropic async clients support `stream=True`. The SDK records
the provider span after the returned async stream is consumed, so stream latency
covers generation through the final chunk. If the application stops consuming a
stream early, close it with `await stream.aclose()` when the provider stream
supports it.

## Flush Behavior

The SDK buffers spans and sends them in the background. Long-running services
can rely on the background transport. Scripts, CLIs and tests should end with:

```python
await llm_obs.shutdown()
```

Use `await llm_obs.shutdown(flush=False)` only when a test intentionally should
discard buffered spans.

## SDK Diagnostics

Use `llm_obs.get_sdk_diagnostics()` to inspect safe client-side telemetry
counters without exposing prompts, outputs, span payloads or API keys:

```python
diagnostics = llm_obs.get_sdk_diagnostics()
if diagnostics:
    print(
        diagnostics.dropped_spans,
        diagnostics.failed_flushes,
        diagnostics.buffered_spans,
        diagnostics.active_buffered_spans,
        diagnostics.pending_spans,
        diagnostics.pending_batches,
    )
```

`buffered_spans` is the total currently held by the SDK. Active spans are waiting
for a new flush; pending spans are in failed batches that will retry before newer
active spans. If `dropped_spans` increases and `last_drop_reason` is
`buffer_overflow`, the active in-memory buffer filled and the oldest active span
was discarded locally.

## Verifying Delivery

Accepted ingest batches return a `batch_id`. Check asynchronous processing with
the project API key:

Repeated ingest requests with the same `idempotency_key` and identical spans
return the original `batch_id` without enqueueing another batch. Reusing the
same idempotency key with a different request body returns `409 Conflict`.
The Python SDK generates an idempotency key for each flush batch automatically
and reuses it for retries of that same batch.
Batch status `processed` counts spans actually inserted into storage; it can be
lower than `accepted` when duplicate span ids are ignored.
See [delivery-guarantees.md](delivery-guarantees.md) for the current
at-most-once, at-least-once and effectively-once boundaries.

```bash
curl -H "X-API-Key: $LLM_OBS_API_KEY" \
  http://localhost:8000/v1/ingest/batches/YOUR_BATCH_ID
```

If a trace is accepted but not visible, check the dashboard time range, the
worker logs and [troubleshooting.md](troubleshooting.md).
