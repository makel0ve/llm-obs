import asyncio

from redis.asyncio import Redis

_redis_client: Redis | None = None
_redis_queue_client: Redis | None = None
_redis_lock = asyncio.Lock()
_redis_queue_lock = asyncio.Lock()


async def get_redis() -> Redis:
    global _redis_client
    if _redis_client is None:
        async with _redis_lock:
            if _redis_client is None:
                from app.core.config import settings

                _redis_client = Redis.from_url(
                    settings.redis_url, encoding="utf-8", decode_responses=True
                )

    return _redis_client


async def get_redis_queue() -> Redis:
    global _redis_queue_client
    if _redis_queue_client is None:
        async with _redis_queue_lock:
            if _redis_queue_client is None:
                from app.core.config import settings

                _redis_queue_client = Redis.from_url(
                    settings.effective_redis_queue_url,
                    encoding="utf-8",
                    decode_responses=True,
                )

    return _redis_queue_client


async def close_redis() -> None:
    global _redis_client, _redis_queue_client
    if _redis_client is not None:
        await _redis_client.close()
        _redis_client = None
    if _redis_queue_client is not None:
        await _redis_queue_client.close()
        _redis_queue_client = None
