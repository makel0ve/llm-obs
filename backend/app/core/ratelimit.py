import time

from fastapi import Depends, HTTPException, Response, status
from redis.asyncio import Redis

from app.core.config import settings
from app.core.redis import get_redis


class RateLimiter:
    def __init__(self, redis: Redis):
        self._redis = redis

    async def check(self, project_id: str, response: Response) -> None:
        now = time.time()
        window = 60
        limit = settings.api_rate_limit_per_minute
        key = f"ratelimit:{project_id}"

        pipe = self._redis.pipeline()
        pipe.zremrangebyscore(key, 0, now - window)
        pipe.zadd(key, {f"{now}:{id(object())}": now})
        pipe.zcard(key)
        pipe.expire(key, window + 1)

        results = await pipe.execute()

        count = results[2]
        remaining = max(0, limit - count)
        response.headers["X-RateLimit-Limit"] = str(limit)
        response.headers["X-RateLimit-Remaining"] = str(remaining)

        if count > limit:
            raise HTTPException(
                status_code=status.HTTP_429_TOO_MANY_REQUESTS,
                detail={"error": "rate_limit_exceeded", "limit": limit},
                headers={
                    "Retry-After": str(window),
                    "X-RateLimit-Limit": str(limit),
                    "X-RateLimit-Remaining": "0",
                },
            )


def get_rate_limiter(redis: Redis = Depends(get_redis)) -> RateLimiter:
    return RateLimiter(redis=redis)
