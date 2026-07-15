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

        async with get_db(project_id=project_id) as db:
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

        async with get_db(project_id=project_id) as db:
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

    async def get_analytics(self, project_id: str, period: str) -> dict:
        interval = PERIOD_TO_INTERVAL[period]
        granularity = PERIOD_TO_GRANULARITY[period]
        cutoff = datetime.now(UTC) - interval

        async with get_db(project_id=project_id) as db:
            cost_by_model = await db.execute(
                text(
                    """
                SELECT
                    COALESCE(model, 'unknown')                    AS model,
                    COALESCE(SUM(cost_usd), 0)                    AS total_cost_usd,
                    COALESCE(SUM(input_tokens + output_tokens), 0) AS total_tokens,
                    COUNT(*)                                      AS span_count
                FROM spans
                WHERE project_id = :project_id
                    AND started_at >= :cutoff
                GROUP BY COALESCE(model, 'unknown')
                ORDER BY total_cost_usd DESC, span_count DESC
                LIMIT 10
                """
                ),
                {"project_id": project_id, "cutoff": cutoff},
            )

            cost_by_provider = await db.execute(
                text(
                    """
                SELECT
                    COALESCE(provider, 'unknown')                 AS provider,
                    COALESCE(SUM(cost_usd), 0)                    AS total_cost_usd,
                    COALESCE(SUM(input_tokens + output_tokens), 0) AS total_tokens,
                    COUNT(*)                                      AS span_count
                FROM spans
                WHERE project_id = :project_id
                    AND started_at >= :cutoff
                GROUP BY COALESCE(provider, 'unknown')
                ORDER BY total_cost_usd DESC, span_count DESC
                LIMIT 10
                """
                ),
                {"project_id": project_id, "cutoff": cutoff},
            )

            cost_over_time = await db.execute(
                text(
                    """
                SELECT
                    date_trunc(:granularity, started_at) AS bucket,
                    COALESCE(SUM(cost_usd), 0)           AS total_cost_usd,
                    COUNT(*)                             AS span_count
                FROM spans
                WHERE project_id = :project_id
                    AND started_at >= :cutoff
                GROUP BY 1
                ORDER BY 1
                """
                ),
                {
                    "granularity": granularity,
                    "project_id": project_id,
                    "cutoff": cutoff,
                },
            )

            latency_by_model = await db.execute(
                text(
                    """
                SELECT
                    COALESCE(model, 'unknown')        AS model,
                    ROUND(AVG(latency_ms)::numeric, 2) AS avg_latency_ms,
                    PERCENTILE_CONT(0.95) WITHIN GROUP
                        (ORDER BY latency_ms)          AS p95_latency_ms,
                    COUNT(*)                          AS span_count
                FROM spans
                WHERE project_id = :project_id
                    AND started_at >= :cutoff
                GROUP BY COALESCE(model, 'unknown')
                ORDER BY p95_latency_ms DESC NULLS LAST, span_count DESC
                LIMIT 10
                """
                ),
                {"project_id": project_id, "cutoff": cutoff},
            )

            latency_by_provider = await db.execute(
                text(
                    """
                SELECT
                    COALESCE(provider, 'unknown')      AS provider,
                    ROUND(AVG(latency_ms)::numeric, 2) AS avg_latency_ms,
                    PERCENTILE_CONT(0.95) WITHIN GROUP
                        (ORDER BY latency_ms)          AS p95_latency_ms,
                    COUNT(*)                          AS span_count
                FROM spans
                WHERE project_id = :project_id
                    AND started_at >= :cutoff
                GROUP BY COALESCE(provider, 'unknown')
                ORDER BY p95_latency_ms DESC NULLS LAST, span_count DESC
                LIMIT 10
                """
                ),
                {"project_id": project_id, "cutoff": cutoff},
            )

            top_expensive_traces = await db.execute(
                text(
                    """
                SELECT
                    trace_id,
                    COALESCE(SUM(cost_usd), 0) AS total_cost_usd,
                    COUNT(*)                   AS span_count,
                    MIN(started_at)            AS started_at
                FROM spans
                WHERE project_id = :project_id
                    AND started_at >= :cutoff
                GROUP BY trace_id
                ORDER BY total_cost_usd DESC, span_count DESC
                LIMIT 10
                """
                ),
                {"project_id": project_id, "cutoff": cutoff},
            )

            slowest_traces = await db.execute(
                text(
                    """
                SELECT
                    trace_id,
                    MAX(latency_ms)                   AS max_latency_ms,
                    ROUND(AVG(latency_ms)::numeric, 2) AS avg_latency_ms,
                    COUNT(*)                          AS span_count,
                    MIN(started_at)                   AS started_at
                FROM spans
                WHERE project_id = :project_id
                    AND started_at >= :cutoff
                GROUP BY trace_id
                ORDER BY max_latency_ms DESC, span_count DESC
                LIMIT 10
                """
                ),
                {"project_id": project_id, "cutoff": cutoff},
            )

            error_rate_trend = await db.execute(
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
                        COUNT(*)                                 AS span_count,
                        COUNT(*) FILTER (WHERE status = 'error') AS error_count
                    FROM spans
                    WHERE project_id = :project_id
                        AND started_at >= :cutoff
                    GROUP BY 1
                )
                SELECT
                    tb.bucket,
                    COALESCE(m.span_count, 0)  AS span_count,
                    COALESCE(m.error_count, 0) AS error_count,
                    COALESCE(
                        ROUND(
                            COALESCE(m.error_count, 0)::numeric
                            / NULLIF(COALESCE(m.span_count, 0), 0) * 100, 2
                        ),
                        0
                    ) AS error_rate_pct
                FROM time_buckets tb
                LEFT JOIN metrics m ON tb.bucket = m.bucket
                ORDER BY tb.bucket
                """
                ),
                {
                    "granularity": granularity,
                    "cutoff": cutoff,
                    "bucket_size": PERIOD_TO_BUCKET_SIZE[period],
                    "project_id": project_id,
                },
            )

            top_error_messages = await db.execute(
                text(
                    """
                SELECT
                    LEFT(COALESCE(NULLIF(error, ''), 'unknown error'), 240)
                        AS error_message,
                    COUNT(*)       AS error_count,
                    MAX(started_at) AS last_seen_at
                FROM spans
                WHERE project_id = :project_id
                    AND started_at >= :cutoff
                    AND status = 'error'
                GROUP BY LEFT(COALESCE(NULLIF(error, ''), 'unknown error'), 240)
                ORDER BY error_count DESC, last_seen_at DESC
                LIMIT 10
                """
                ),
                {"project_id": project_id, "cutoff": cutoff},
            )

            errors_by_model = await db.execute(
                text(
                    """
                SELECT
                    COALESCE(model, 'unknown')                  AS model,
                    COUNT(*)                                    AS span_count,
                    COUNT(*) FILTER (WHERE status = 'error')    AS error_count,
                    ROUND(
                        (COUNT(*) FILTER (WHERE status = 'error'))::numeric
                        / NULLIF(COUNT(*), 0) * 100, 2
                    )                                           AS error_rate_pct
                FROM spans
                WHERE project_id = :project_id
                    AND started_at >= :cutoff
                GROUP BY COALESCE(model, 'unknown')
                ORDER BY error_count DESC, error_rate_pct DESC NULLS LAST
                LIMIT 10
                """
                ),
                {"project_id": project_id, "cutoff": cutoff},
            )

            errors_by_provider = await db.execute(
                text(
                    """
                SELECT
                    COALESCE(provider, 'unknown')               AS provider,
                    COUNT(*)                                    AS span_count,
                    COUNT(*) FILTER (WHERE status = 'error')    AS error_count,
                    ROUND(
                        (COUNT(*) FILTER (WHERE status = 'error'))::numeric
                        / NULLIF(COUNT(*), 0) * 100, 2
                    )                                           AS error_rate_pct
                FROM spans
                WHERE project_id = :project_id
                    AND started_at >= :cutoff
                GROUP BY COALESCE(provider, 'unknown')
                ORDER BY error_count DESC, error_rate_pct DESC NULLS LAST
                LIMIT 10
                """
                ),
                {"project_id": project_id, "cutoff": cutoff},
            )

            recent_failed_traces = await db.execute(
                text(
                    """
                SELECT
                    trace_id,
                    MAX(started_at) AS started_at,
                    COUNT(*)        AS error_count,
                    LEFT(
                        (ARRAY_AGG(
                            COALESCE(NULLIF(error, ''), 'unknown error')
                            ORDER BY started_at DESC
                        ))[1],
                        240
                    ) AS error_message
                FROM spans
                WHERE project_id = :project_id
                    AND started_at >= :cutoff
                    AND status = 'error'
                GROUP BY trace_id
                ORDER BY started_at DESC
                LIMIT 10
                """
                ),
                {"project_id": project_id, "cutoff": cutoff},
            )

            error_fingerprints = await db.execute(
                text(
                    """
                WITH error_source AS (
                    SELECT
                        trace_id,
                        COALESCE(provider, 'unknown') AS provider,
                        COALESCE(model, 'unknown')    AS model,
                        started_at,
                        COALESCE(NULLIF(error, ''), 'unknown error') AS error_message
                    FROM spans
                    WHERE project_id = :project_id
                        AND started_at >= :cutoff
                        AND status = 'error'
                ),
                error_rows AS (
                    SELECT
                        trace_id,
                        provider,
                        model,
                        started_at,
                        LEFT(
                            regexp_replace(
                                regexp_replace(
                                    error_message,
                                    '[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}',
                                    '<uuid>',
                                    'gi'
                                ),
                                '(sk-[A-Za-z0-9_-]+|llmobs_[A-Za-z0-9_-]+)',
                                '<secret>',
                                'gi'
                            ),
                            240
                        ) AS sample_message,
                        LEFT(
                            regexp_replace(
                                regexp_replace(
                                    regexp_replace(
                                        lower(
                                            regexp_replace(
                                                regexp_replace(
                                                    error_message,
                                                    '[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}',
                                                    '<uuid>',
                                                    'gi'
                                                ),
                                                '(sk-[A-Za-z0-9_-]+|llmobs_[A-Za-z0-9_-]+)',
                                                '<secret>',
                                                'gi'
                                            )
                                        ),
                                        '[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}',
                                        '<uuid>',
                                        'gi'
                                    ),
                                    '\\m[0-9]+\\M',
                                    '<num>',
                                    'g'
                                ),
                                '\\s+',
                                ' ',
                                'g'
                            ),
                            160
                        ) AS fingerprint
                    FROM error_source
                ),
                grouped AS (
                    SELECT
                        fingerprint,
                        COUNT(*)                 AS error_count,
                        COUNT(DISTINCT trace_id) AS affected_trace_count,
                        MAX(started_at)          AS last_seen_at,
                        (ARRAY_AGG(sample_message ORDER BY started_at DESC))[1]
                            AS sample_message
                    FROM error_rows
                    GROUP BY fingerprint
                ),
                provider_rank AS (
                    SELECT
                        fingerprint,
                        provider,
                        ROW_NUMBER() OVER (
                            PARTITION BY fingerprint
                            ORDER BY COUNT(*) DESC, provider ASC
                        ) AS rank
                    FROM error_rows
                    GROUP BY fingerprint, provider
                ),
                model_rank AS (
                    SELECT
                        fingerprint,
                        model,
                        ROW_NUMBER() OVER (
                            PARTITION BY fingerprint
                            ORDER BY COUNT(*) DESC, model ASC
                        ) AS rank
                    FROM error_rows
                    GROUP BY fingerprint, model
                )
                SELECT
                    g.fingerprint,
                    g.sample_message,
                    g.error_count,
                    g.affected_trace_count,
                    pr.provider AS top_provider,
                    mr.model    AS top_model,
                    g.last_seen_at
                FROM grouped g
                LEFT JOIN provider_rank pr
                    ON pr.fingerprint = g.fingerprint AND pr.rank = 1
                LEFT JOIN model_rank mr
                    ON mr.fingerprint = g.fingerprint AND mr.rank = 1
                ORDER BY g.error_count DESC, g.last_seen_at DESC
                LIMIT 10
                """
                ),
                {"project_id": project_id, "cutoff": cutoff},
            )

        return {
            "cost_by_model": [dict(row) for row in cost_by_model.mappings().all()],
            "cost_by_provider": [
                dict(row) for row in cost_by_provider.mappings().all()
            ],
            "cost_over_time": [dict(row) for row in cost_over_time.mappings().all()],
            "latency_by_model": [
                dict(row) for row in latency_by_model.mappings().all()
            ],
            "latency_by_provider": [
                dict(row) for row in latency_by_provider.mappings().all()
            ],
            "top_expensive_traces": [
                dict(row) for row in top_expensive_traces.mappings().all()
            ],
            "slowest_traces": [dict(row) for row in slowest_traces.mappings().all()],
            "error_rate_trend": [
                dict(row) for row in error_rate_trend.mappings().all()
            ],
            "top_error_messages": [
                dict(row) for row in top_error_messages.mappings().all()
            ],
            "errors_by_model": [dict(row) for row in errors_by_model.mappings().all()],
            "errors_by_provider": [
                dict(row) for row in errors_by_provider.mappings().all()
            ],
            "recent_failed_traces": [
                dict(row) for row in recent_failed_traces.mappings().all()
            ],
            "error_fingerprints": [
                dict(row) for row in error_fingerprints.mappings().all()
            ],
        }
