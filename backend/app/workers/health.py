from datetime import UTC, datetime

import structlog

from app.core.config import settings
from app.core.redis import get_redis
from app.core.taskiq import broker

WORKER_HEARTBEAT_KEY = "llmobs:health:worker:last_seen"

log = structlog.get_logger()


async def write_worker_heartbeat() -> str:
    seen_at = datetime.now(UTC).isoformat()
    redis = await get_redis()
    await redis.set(
        WORKER_HEARTBEAT_KEY,
        seen_at,
        ex=settings.worker_heartbeat_ttl_seconds,
    )
    return seen_at


@broker.task(schedule=[{"cron": "* * * * *"}])
async def record_worker_heartbeat() -> None:
    seen_at = await write_worker_heartbeat()
    log.debug("worker_heartbeat_recorded", seen_at=seen_at)
