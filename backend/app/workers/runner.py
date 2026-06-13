import asyncio
import signal

import structlog

from app.core.taskiq import broker

log = structlog.get_logger()


async def run_worker():
    shutdown = asyncio.Event()

    def on_sigterm():
        log.info("sigterm_received")
        shutdown.set()

    loop = asyncio.get_event_loop()
    loop.add_signal_handler(signal.SIGTERM, on_sigterm)
    loop.add_signal_handler(signal.SIGINT, on_sigterm)

    await broker.startup()
    log.info("worker_started")
    await shutdown.wait()

    log.info("worker_draining")
    try:
        await asyncio.wait_for(broker.shutdown(), timeout=30.0)
        log.info("worker_stopped")

    except TimeoutError:
        log.warning("worker_shutdown_timeout", timeout=30.0)


if __name__ == "__main__":
    asyncio.run(run_worker())
