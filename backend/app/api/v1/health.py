from datetime import UTC, datetime
from typing import Any

import structlog
from fastapi import APIRouter, HTTPException
from sqlalchemy import text

from app.core.config import settings
from app.core.db import get_db
from app.core.redis import get_redis
from app.workers.health import WORKER_HEARTBEAT_KEY

router = APIRouter(tags=["health"])
log = structlog.get_logger()


@router.get("/health")
async def liveness() -> dict[str, str]:
    return {"status": "ok"}


@router.get("/ready")
async def readiness() -> dict[str, Any]:
    checks: dict[str, str] = {}
    ok = True

    try:
        async with get_db() as db:
            await db.execute(text("SELECT 1"))

        checks["postgres"] = "ok"

    except Exception as e:
        checks["postgres"] = "error"
        ok = False
        log.error("readiness_postgres_failed", error=str(e))

    try:
        redis = await get_redis()
        await redis.ping()
        checks["redis"] = "ok"

    except Exception as e:
        checks["redis"] = "error"
        ok = False
        log.error("readiness_redis_failed", error=str(e))

    if not ok:
        raise HTTPException(status_code=503, detail=checks)

    return {"status": "ready", "checks": checks}


@router.get("/worker-health")
async def worker_health() -> dict[str, Any]:
    try:
        redis = await get_redis()
        last_seen_raw = await redis.get(WORKER_HEARTBEAT_KEY)

    except Exception as e:
        log.error("worker_health_redis_failed", error=str(e))
        raise HTTPException(
            status_code=503,
            detail={"status": "error", "worker": "redis error"},
        ) from e

    max_age = settings.worker_heartbeat_max_age_seconds
    if not last_seen_raw:
        raise HTTPException(
            status_code=503,
            detail={
                "status": "missing",
                "worker": {
                    "last_seen": None,
                    "age_seconds": None,
                    "max_age_seconds": max_age,
                },
            },
        )

    try:
        last_seen = datetime.fromisoformat(str(last_seen_raw))

    except ValueError as e:
        log.error("worker_health_invalid_heartbeat", value=str(last_seen_raw))
        raise HTTPException(
            status_code=503,
            detail={
                "status": "invalid",
                "worker": {
                    "last_seen": str(last_seen_raw),
                    "age_seconds": None,
                    "max_age_seconds": max_age,
                },
            },
        ) from e

    age_seconds = max(0, int((datetime.now(UTC) - last_seen).total_seconds()))
    payload = {
        "last_seen": last_seen.isoformat(),
        "age_seconds": age_seconds,
        "max_age_seconds": max_age,
    }

    if age_seconds > max_age:
        raise HTTPException(
            status_code=503,
            detail={"status": "stale", "worker": payload},
        )

    return {"status": "ok", "worker": payload}
