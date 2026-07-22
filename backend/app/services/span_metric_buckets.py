import json
from collections import defaultdict
from datetime import datetime
from decimal import Decimal
from typing import Any

from sqlalchemy import text


def floor_to_minute(value: datetime) -> datetime:
    return value.replace(second=0, microsecond=0)


async def update_span_metric_buckets(
    db: Any, project_id: str, spans: list[dict[str, Any]]
) -> None:
    if not spans:
        return

    buckets: dict[datetime, dict[str, Decimal | int]] = defaultdict(
        lambda: {
            "span_count": 0,
            "error_count": 0,
            "total_cost_usd": Decimal("0"),
            "latency_sum_ms": Decimal("0"),
        }
    )

    for span in spans:
        bucket_start = floor_to_minute(span["started_at"])
        bucket = buckets[bucket_start]
        bucket["span_count"] = int(bucket["span_count"]) + 1
        bucket["error_count"] = int(bucket["error_count"]) + (
            1 if span["status"] == "error" else 0
        )
        bucket["total_cost_usd"] = Decimal(str(bucket["total_cost_usd"])) + Decimal(
            str(span["cost_usd"])
        )
        bucket["latency_sum_ms"] = Decimal(str(bucket["latency_sum_ms"])) + Decimal(
            str(span["latency_ms"])
        )

    await db.execute(
        text(
            """
            INSERT INTO span_metric_buckets (
                project_id, bucket_start, span_count, error_count, total_cost_usd,
                latency_sum_ms
            )
            SELECT
                :project_id,
                row.bucket_start,
                row.span_count,
                row.error_count,
                row.total_cost_usd,
                row.latency_sum_ms
            FROM jsonb_to_recordset(CAST(:buckets_json AS jsonb)) AS row(
                bucket_start timestamptz,
                span_count integer,
                error_count integer,
                total_cost_usd numeric,
                latency_sum_ms numeric
            )
            ON CONFLICT (project_id, bucket_start) DO UPDATE SET
                span_count = span_metric_buckets.span_count + EXCLUDED.span_count,
                error_count = span_metric_buckets.error_count + EXCLUDED.error_count,
                total_cost_usd =
                    span_metric_buckets.total_cost_usd + EXCLUDED.total_cost_usd,
                latency_sum_ms =
                    span_metric_buckets.latency_sum_ms + EXCLUDED.latency_sum_ms,
                updated_at = TIMEZONE('utc', now())
            """
        ),
        {
            "project_id": project_id,
            "buckets_json": json.dumps(_bucket_payload(buckets)),
        },
    )


def _bucket_payload(
    buckets: dict[datetime, dict[str, Decimal | int]],
) -> list[dict[str, str | int]]:
    return [
        {
            "bucket_start": bucket_start.isoformat(),
            "span_count": int(values["span_count"]),
            "error_count": int(values["error_count"]),
            "total_cost_usd": str(values["total_cost_usd"]),
            "latency_sum_ms": str(values["latency_sum_ms"]),
        }
        for bucket_start, values in sorted(buckets.items())
    ]


async def query_bucketed_alert_value(
    db: Any, project_id: str, metric: str, window_minutes: int
) -> tuple[float, int]:
    if metric == "error_rate":
        result = await db.execute(
            text(
                """
                SELECT
                    CASE WHEN COALESCE(SUM(span_count), 0) = 0 THEN 0
                        ELSE (
                            COALESCE(SUM(error_count), 0)::float
                            / SUM(span_count)::float
                        ) * 100
                    END AS value,
                    COALESCE(SUM(span_count), 0) AS sample_count
                FROM span_metric_buckets
                WHERE project_id = :project_id
                    AND bucket_start >= date_trunc(
                        'minute',
                        NOW() - make_interval(mins => :window_minutes)
                    )
                """
            ),
            {"project_id": project_id, "window_minutes": window_minutes},
        )
    elif metric == "cost_hourly":
        result = await db.execute(
            text(
                """
                SELECT
                    COALESCE(SUM(total_cost_usd), 0) AS value,
                    COALESCE(SUM(span_count), 0) AS sample_count
                FROM span_metric_buckets
                WHERE project_id = :project_id
                    AND bucket_start >= date_trunc(
                        'minute',
                        NOW() - make_interval(mins => :window_minutes)
                    )
                """
            ),
            {"project_id": project_id, "window_minutes": window_minutes},
        )
    else:
        raise ValueError(f"Unsupported bucketed alert metric: {metric}")

    row = result.mappings().one()
    return float(row["value"] or 0), int(row["sample_count"] or 0)
