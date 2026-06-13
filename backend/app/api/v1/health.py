import structlog
from fastapi import APIRouter, HTTPException
from sqlalchemy import text

from app.core.db import get_db
from app.core.redis import get_redis

router = APIRouter(tags=["health"])
log = structlog.get_logger()


@router.get("/health")
async def liveness() -> dict:
    return {"status": "ok"}


@router.get("/ready")
async def readiness() -> dict:
    checks = {}
    ok = True

    try:
        async with get_db() as db:
            await db.execute(text("SELECT 1"))

        checks["postgres"] = "ok"

    except Exception as e:
        checks["postgres"] = f"error: {e}"
        ok = False
        log.error("readiness_postgres_failed", error=str(e))

    try:
        redis = await get_redis()
        await redis.ping()  # type: ignore[misc]
        checks["redis"] = "ok"

    except Exception as e:
        checks["redis"] = f"error: {e}"
        ok = False
        log.error("readiness_redis_failed", error=str(e))

    if not ok:
        raise HTTPException(status_code=503, detail=checks)

    return {"status": "ready", "checks": checks}
