import asyncio
import os
import threading

from llm_obs.tracer import LLMTracer
from llm_obs.transport import TransportDiagnostics


_tracer_lock = threading.Lock()
_tracer_instance: LLMTracer | None = None


def _env_debug_enabled() -> bool:
    value = os.getenv("LLM_OBS_DEBUG", "")
    return value.lower() in {"1", "true", "yes", "on"}


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
    debug: bool | None = None,
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
            debug=_env_debug_enabled() if debug is None else debug,
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
            _tracer_instance = LLMTracer(
                api_key=api_key,
                endpoint=endpoint,
                debug=_env_debug_enabled(),
            )
            _schedule_start(_tracer_instance)

    return _tracer_instance


def get_tracer() -> LLMTracer | None:
    return _tracer_instance


def get_diagnostics() -> TransportDiagnostics | None:
    tracer = _tracer_instance
    if tracer is None:
        return None

    return tracer.last_flush_diagnostics


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


from llm_obs.decorators import ManualSpan as ManualSpan  # noqa: E402
from llm_obs.decorators import span as span  # noqa: E402
from llm_obs.decorators import trace as trace  # noqa: E402

__all__ = [
    "LLMTracer",
    "ManualSpan",
    "TransportDiagnostics",
    "get_diagnostics",
    "get_tracer",
    "init",
    "shutdown",
    "span",
    "trace",
]
