"""Send one safe demo span to LLM Obs.

Required environment:
  LLM_OBS_API_KEY=llmobs_your_key_here
  LLM_OBS_ENDPOINT=http://localhost:8000
"""

import asyncio
import os
import sys

import llm_obs  # type: ignore[import-not-found]


@llm_obs.trace(name="examples.sdk_smoke_demo", metadata={"example": "sdk_smoke_demo"})
async def demo_llm_call(prompt: str) -> str:
    async with llm_obs.span(
        "examples.sdk_smoke_demo.manual_step",
        provider="custom",
        model="demo-model",
        input_messages=[{"role": "user", "content": prompt}],
        metadata={"example": "manual_span"},
    ) as span:
        await asyncio.sleep(0.05)
        response = f"demo response for: {prompt}"
        span.set_output(response)
        span.set_tokens(input_tokens=8, output_tokens=6)
        return response


async def main() -> int:
    if not os.getenv("LLM_OBS_API_KEY"):
        print("Set LLM_OBS_API_KEY before running this example.", file=sys.stderr)
        return 2

    endpoint = os.getenv("LLM_OBS_ENDPOINT", "http://localhost:8000")
    response = await demo_llm_call("Hello from the SDK smoke example")
    await llm_obs.shutdown()

    print(f"Sent demo span to {endpoint}")
    print(response)
    return 0


if __name__ == "__main__":
    raise SystemExit(asyncio.run(main()))
