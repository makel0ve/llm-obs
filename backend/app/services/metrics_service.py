from datetime import UTC, datetime, timedelta

from sqlalchemy import text

from app.core.db import get_db

PERIOD_TO_INTERVAL = {
    "1h": timedelta(hours=1),
    "24h": timedelta(hours=24),
    "7d": timedelta(days=7),
    "30d": timedelta(days=30),
}

PERIOD_TO_BUCKET_SIZE = {
    "1h": timedelta(minutes=1),
    "24h": timedelta(hours=1),
    "7d": timedelta(hours=1),
    "30d": timedelta(days=1),
}

PERIOD_TO_GRANULARITY = {
    "1h": "minute",
    "24h": "hour",
    "7d": "hour",
    "30d": "day",
}


class MetricsService:
    async def get_overview(self, project_id: str, period: str) -> dict:
        interval = PERIOD_TO_INTERVAL[period]
        cutoff = datetime.now(UTC) - interval

        async with get_db() as db:
            result = await db.execute(
                text(
                    """
                SELECT
                    COUNT(*)                                       AS total_spans,
                    COUNT(*) FILTER (WHERE status = 'error')       AS error_count,
                    ROUND(
                        (COUNT(*) FILTER (WHERE status = 'error'))::numeric
                        / NULLIF(COUNT(*), 0) * 100, 2
                    )                                              AS error_rate_pct,
                    ROUND(AVG(latency_ms)::numeric, 2)             AS avg_latency_ms,
                    PERCENTILE_CONT(0.95) WITHIN GROUP
                        (ORDER BY latency_ms)                      AS p95_latency_ms,
                    PERCENTILE_CONT(0.99) WITHIN GROUP
                        (ORDER BY latency_ms)                      AS p99_latency_ms,
                    COALESCE(SUM(cost_usd), 0)                     AS total_cost_usd,
                    COALESCE(SUM(input_tokens + output_tokens), 0) AS total_tokens
                FROM spans
                WHERE project_id = :project_id
                    AND started_at >= :cutoff
                """
                ),
                {"project_id": project_id, "cutoff": cutoff},
            )

            row = result.mappings().one_or_none()
            if not row:
                return {}

            return dict(row)

    async def get_timeseries(self, project_id: str, period: str) -> list[dict]:
        interval = PERIOD_TO_INTERVAL[period]
        granularity = PERIOD_TO_GRANULARITY[period]
        bucket_size = PERIOD_TO_BUCKET_SIZE[period]
        cutoff = datetime.now(UTC) - interval

        async with get_db() as db:
            result = await db.execute(
                text(
                    """
                WITH time_buckets AS (
                    SELECT generate_series(
                        date_trunc(:granularity, CAST(:cutoff AS timestamptz)),
                        date_trunc(:granularity, NOW()),
                        CAST(:bucket_size AS interval)
                    ) AS bucket
                ),
                metrics AS (
                    SELECT
                        date_trunc(:granularity, started_at)     AS bucket,
                        SUM(cost_usd)                            AS cost,
                        AVG(latency_ms)                          AS avg_latency,
                        COUNT(*)                                 AS span_count,
                        COUNT(*) FILTER (WHERE status = 'error') AS error_count
                    FROM spans
                    WHERE project_id = :project_id
                        AND started_at >= :cutoff
                    GROUP BY 1
                )
                SELECT
                    tb.bucket,
                    COALESCE(m.cost, 0)        AS cost,
                    COALESCE(m.avg_latency, 0) AS avg_latency,
                    COALESCE(m.span_count, 0)  AS span_count,
                    COALESCE(m.error_count, 0) AS error_count
                FROM time_buckets tb
                LEFT JOIN metrics m ON tb.bucket = m.bucket
                ORDER BY tb.bucket
                """
                ),
                {
                    "granularity": granularity,
                    "cutoff": cutoff,
                    "bucket_size": bucket_size,
                    "project_id": project_id,
                },
            )

            rows = result.mappings().all()

        return [dict(r) for r in rows]
