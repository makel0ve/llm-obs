import asyncio
import os
import threading

from llm_obs.tracer import LLMTracer


_tracer_lock = threading.Lock()
_tracer_instance: LLMTracer | None = None


def _schedule_start(tracer: LLMTracer) -> None:
    try:
        loop = asyncio.get_event_loop()
        if loop.is_running():
            loop.create_task(tracer.start())

        else:
            asyncio.ensure_future(tracer.start())

    except RuntimeError:
        pass


def init(
    api_key: str,
    endpoint: str = "http://localhost:8000",
    *,
    buffer_size: int = 500,
    flush_interval: float = 5.0,
    start: bool = True,
) -> LLMTracer:
    global _tracer_instance

    with _tracer_lock:
        if _tracer_instance is not None:
            raise RuntimeError("llm_obs tracer is already initialized")

        _tracer_instance = LLMTracer(
            api_key=api_key,
            endpoint=endpoint,
            buffer_size=buffer_size,
            flush_interval=flush_interval,
        )

        if start:
            _schedule_start(_tracer_instance)

        return _tracer_instance


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
            _schedule_start(_tracer_instance)

    return _tracer_instance


def get_tracer() -> LLMTracer | None:
    return _tracer_instance


async def shutdown(*, flush: bool = True) -> None:
    global _tracer_instance

    with _tracer_lock:
        tracer = _tracer_instance
        _tracer_instance = None

    if tracer is not None:
        await tracer.shutdown(flush=flush)


def _get_tracer() -> LLMTracer:
    tracer = _get_or_create_tracer()
    if tracer is None:
        raise RuntimeError("llm_obs tracer is not initialized")

    return tracer


from llm_obs.decorators import trace as trace  # noqa: E402

__all__ = ["LLMTracer", "get_tracer", "init", "shutdown", "trace"]
