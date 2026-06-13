import asyncio
import os
import threading

from llm_obs.tracer import LLMTracer


_tracer_lock = threading.Lock()
_tracer_instance: LLMTracer | None = None


def _get_or_create_tracer() -> LLMTracer | None:
    global _tracer_instance

    if _tracer_instance is not None:
        return _tracer_instance

    api_key = os.getenv("LLM_OBS_API_KEY")
    endpoint = os.getenv("LLM_OBS_ENDPOINT", "http://localhost:8000")

    if not api_key:
        return None

    with _tracer_lock:
        if _tracer_instance is None:
            _tracer_instance = LLMTracer(api_key=api_key, endpoint=endpoint)

            try:
                loop = asyncio.get_event_loop()
                if loop.is_running():
                    loop.create_task(_tracer_instance.start())

                else:
                    asyncio.ensure_future(_tracer_instance.start())

            except RuntimeError:
                pass

    return _tracer_instance


def get_tracer() -> LLMTracer | None:
    return _tracer_instance


from llm_obs.decorators import trace as trace  # noqa: E402
