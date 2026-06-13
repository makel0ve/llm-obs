import json

from fastapi import APIRouter, Depends, Query
from redis.asyncio import Redis

from app.core.auth import get_project_from_token_or_api_key
from app.core.redis import get_redis
from app.services.metrics_service import MetricsService

router = APIRouter(prefix="/v1", tags=["metrics"])


@router.get("/metrics/overview")
async def get_metrics_overview(
    project=Depends(get_project_from_token_or_api_key),
    period: str = Query(default="24h", pattern="^(1h|24h|7d|30d)$"),
    redis: Redis = Depends(get_redis),
):
    cache_key = f"metrics:overview:{project['id']}:{period}"
    cached = await redis.get(cache_key)
    if cached:
        return json.loads(cached)

    result = await MetricsService().get_overview(str(project["id"]), period)
    ttl = {"1h": 30, "24h": 60, "7d": 300, "30d": 300}[period]
    await redis.setex(cache_key, ttl, json.dumps(result, default=str))

    return result


@router.get("/metrics/timeseries")
async def get_metrics_timeseries(
    project=Depends(get_project_from_token_or_api_key),
    period: str = Query(default="24h", pattern="^(1h|24h|7d|30d)$"),
    redis: Redis = Depends(get_redis),
):
    cache_key = f"metrics:timeseries:{project['id']}:{period}"
    cached = await redis.get(cache_key)
    if cached:
        return json.loads(cached)

    result = await MetricsService().get_timeseries(str(project["id"]), period)
    ttl = {"1h": 30, "24h": 60, "7d": 300, "30d": 300}[period]
    await redis.setex(cache_key, ttl, json.dumps(result, default=str))

    return result
