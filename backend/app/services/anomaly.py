import json

from sqlalchemy import text

from app.core.db import get_db
from app.core.redis import get_redis


class AnomalyService:
    Z_SCORE_THRESHOLD = 3.0
    MIN_OBSERVATIONS = 30
    STATS_CACHE_TTL = 300

    async def check(self, project_id: str, span: dict) -> list[str]:
        anomalies = []
        if await self._latency_anomaly(project_id, span):
            anomalies.append("latency_spike")

        if await self._error_rate_anomaly(project_id, span["model"]):
            anomalies.append("high_error_rate")

        return anomalies

    async def _latency_anomaly(self, project_id: str, span: dict) -> bool:
        stats = await self._get_stats_cached(project_id, span["model"])
        if not stats or stats["count"] < self.MIN_OBSERVATIONS or stats["stddev"] == 0:
            return False

        z = (span["latency_ms"] - stats["mean"]) / stats["stddev"]

        return abs(z) > self.Z_SCORE_THRESHOLD

    async def _error_rate_anomaly(self, project_id: str, model: str) -> bool:
        async with get_db() as db:
            r = await db.execute(
                text(
                    """
                SELECT COUNT(*) AS total,
                    COUNT(*) FILTER (WHERE status = 'error') AS errors
                FROM spans
                WHERE project_id = :pid AND model = :m
                    AND started_at >= NOW() - INTERVAL '5 minutes'
                """
                ),
                {"pid": project_id, "m": model},
            )

            row = r.mappings().one()

        if not row["total"]:
            return False

        if row["total"] < 10:
            return False

        return (row["errors"] / row["total"]) > 0.10

    async def _get_stats_cached(self, project_id: str, model: str) -> dict | None:
        key = f"stats:{project_id}:{model}"
        redis = await get_redis()
        cached = await redis.get(key)
        if cached:
            return json.loads(cached)

        async with get_db() as db:
            r = await db.execute(
                text(
                    """
                SELECT AVG(latency_ms) as mean,
                    STDDEV(latency_ms) as stddev,
                    COUNT(*) as count
                FROM spans
                WHERE project_id = :pid AND model = :m
                    AND started_at >= NOW() - INTERVAL '24 hours'
                    AND status = 'ok'
                """
                ),
                {"pid": project_id, "m": model},
            )

            row = r.mappings().one_or_none()

        if not row or not row["count"]:
            return None

        stats = {
            "mean": float(row["mean"]),
            "stddev": float(row["stddev"] or 0),
            "count": int(row["count"]),
        }
        await redis.setex(key, self.STATS_CACHE_TTL, json.dumps(stats))

        return stats
