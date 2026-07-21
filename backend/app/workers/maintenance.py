import json
from datetime import UTC, datetime, timedelta

import aioboto3
import structlog
from sqlalchemy import text

from app.core.config import settings
from app.core.db import get_db, get_maintenance_db
from app.core.taskiq import broker

log = structlog.get_logger()
RETENTION_BATCH_SIZE = 1000
S3_DELETE_BATCH_SIZE = 1000
PARTITION_LOOKAHEAD_MONTHS = 2


def _is_project_payload_key(project_id: str, key: str) -> bool:
    return key.startswith(f"payloads/{project_id}/")


async def _delete_s3_objects(project_id: str, s3_keys: list[str]) -> set[str]:
    safe_keys = [key for key in s3_keys if _is_project_payload_key(project_id, key)]
    unsafe_keys = sorted(set(s3_keys) - set(safe_keys))
    for key in unsafe_keys:
        log.warning(
            "retention_skipped_unsafe_payload_key", project_id=project_id, key=key
        )

    if not safe_keys:
        return set()

    deleted_keys: set[str] = set()
    try:
        session = aioboto3.Session()
        async with session.client(
            "s3",
            endpoint_url=settings.s3_endpoint_url,
            aws_access_key_id=settings.aws_access_key_id.get_secret_value(),
            aws_secret_access_key=settings.aws_secret_access_key.get_secret_value(),
        ) as s3:
            for i in range(0, len(safe_keys), S3_DELETE_BATCH_SIZE):
                batch = safe_keys[i : i + S3_DELETE_BATCH_SIZE]
                response = await s3.delete_objects(
                    Bucket=settings.s3_bucket,
                    Delete={
                        "Objects": [{"Key": k} for k in batch],
                        "Quiet": True,
                    },
                )

                failed_keys = {
                    str(error.get("Key"))
                    for error in response.get("Errors", [])
                    if error.get("Key")
                }
                successful_keys = set(batch) - failed_keys
                deleted_keys.update(successful_keys)
                log.info(
                    "s3_objects_deleted",
                    project_id=project_id,
                    count=len(successful_keys),
                    failed=len(failed_keys),
                )

    except Exception as e:
        log.error(
            "s3_delete_failed",
            project_id=project_id,
            count=len(safe_keys),
            error=str(e),
        )

    return deleted_keys


async def _fetch_retention_batch(db, project_id: str, cutoff: datetime) -> list[dict]:
    result = await db.execute(
        text(
            """
            SELECT id, started_at, payload_s3_key
            FROM spans
            WHERE project_id = :pid AND started_at < :cutoff
            ORDER BY started_at ASC
            LIMIT :limit
            """
        ),
        {"pid": project_id, "cutoff": cutoff, "limit": RETENTION_BATCH_SIZE},
    )
    return [dict(row) for row in result.mappings().all()]


async def _delete_span_batch(db, project_id: str, span_keys: list[dict]) -> int:
    if not span_keys:
        return 0

    serialized_span_keys = [
        {
            "id": str(row["id"]),
            "started_at": row["started_at"].isoformat()
            if isinstance(row["started_at"], datetime)
            else str(row["started_at"]),
        }
        for row in span_keys
    ]
    result = await db.execute(
        text(
            """
            WITH selected_spans AS (
                SELECT id::uuid, started_at::timestamptz
                FROM jsonb_to_recordset(CAST(:span_keys AS jsonb))
                    AS selected(id text, started_at text)
            )
            DELETE FROM spans
            USING selected_spans
            WHERE spans.project_id = :pid
                AND spans.id = selected_spans.id
                AND spans.started_at = selected_spans.started_at
            """
        ),
        {"pid": project_id, "span_keys": json.dumps(serialized_span_keys)},
    )
    await db.commit()
    return int(result.rowcount or 0)


async def _delete_stale_traces(db, project_id: str, cutoff: datetime) -> int:
    result = await db.execute(
        text(
            """
            DELETE FROM traces t
            WHERE t.project_id = :pid
                AND t.started_at < :cutoff
                AND NOT EXISTS (
                    SELECT 1
                    FROM spans s
                    WHERE s.project_id = t.project_id
                        AND s.trace_id = t.id
                )
            """
        ),
        {"pid": project_id, "cutoff": cutoff},
    )
    await db.commit()
    return int(result.rowcount or 0)


def _month_start(dt: datetime) -> datetime:
    return datetime(dt.year, dt.month, 1, tzinfo=UTC)


def _add_months(month_start: datetime, months: int) -> datetime:
    month_index = month_start.month - 1 + months
    year = month_start.year + month_index // 12
    month = month_index % 12 + 1
    return datetime(year, month, 1, tzinfo=UTC)


def _partition_suffix(month_start: datetime) -> str:
    return f"{month_start.year}_{month_start.month:02d}"


def _future_partition_months(
    now: datetime, lookahead_months: int = PARTITION_LOOKAHEAD_MONTHS
) -> list[datetime]:
    current_month = _month_start(now)
    return [
        _add_months(current_month, offset) for offset in range(1, lookahead_months + 1)
    ]


async def _default_partition_row_count(
    db, table_name: str, start: datetime | None = None, end: datetime | None = None
) -> int:
    if table_name not in {"spans", "traces"}:
        raise ValueError("Unsupported partitioned table")

    time_filter = ""
    params: dict[str, datetime] = {}
    if start is not None and end is not None:
        time_filter = "WHERE started_at >= :start AND started_at < :end"
        params = {"start": start, "end": end}

    result = await db.execute(
        text(
            f"""
            SELECT COUNT(*) AS row_count
            FROM {table_name}_default
            {time_filter}
            """  # nosec B608
        ),
        params,
    )
    row = result.mappings().one()
    return int(row["row_count"])


async def _log_default_partition_growth(db) -> dict[str, int]:
    counts = {
        table_name: await _default_partition_row_count(db, table_name)
        for table_name in ("spans", "traces")
    }
    for table_name, row_count in counts.items():
        if row_count > 0:
            log.warning(
                "default_partition_has_rows",
                table=table_name,
                row_count=row_count,
            )
        else:
            log.info("default_partition_empty", table=table_name)

    return counts


async def _create_month_partition(db, table_name: str, month_start: datetime) -> bool:
    if table_name not in {"spans", "traces"}:
        raise ValueError("Unsupported partitioned table")

    month_end = _add_months(month_start, 1)
    suffix = _partition_suffix(month_start)
    default_rows = await _default_partition_row_count(
        db, table_name, start=month_start, end=month_end
    )
    if default_rows > 0:
        log.warning(
            "partition_creation_skipped_default_rows",
            table=table_name,
            suffix=suffix,
            default_rows=default_rows,
        )
        return False

    partition_name = f"{table_name}_{suffix}"
    start_str = month_start.date().isoformat()
    end_str = month_end.date().isoformat()
    await db.execute(
        text(
            f"""
            CREATE TABLE IF NOT EXISTS {partition_name}
            PARTITION OF {table_name}
            FOR VALUES FROM ('{start_str}') TO ('{end_str}')
            """  # nosec B608
        )
    )
    await db.execute(
        text(
            f"""
            ALTER TABLE {partition_name} ENABLE ROW LEVEL SECURITY
            """  # nosec B608
        )
    )
    await db.execute(
        text(
            f"""
            ALTER TABLE {partition_name} FORCE ROW LEVEL SECURITY
            """  # nosec B608
        )
    )
    return True


@broker.task(schedule=[{"cron": "0 1 * * *"}])
async def create_next_month_partition(
    now: datetime | None = None,
    lookahead_months: int = PARTITION_LOOKAHEAD_MONTHS,
) -> None:
    now = now or datetime.now(UTC)

    async with get_maintenance_db() as db:
        try:
            await _log_default_partition_growth(db)
            created: list[str] = []
            skipped: list[str] = []
            for month_start in _future_partition_months(now, lookahead_months):
                suffix = _partition_suffix(month_start)
                for table_name in ("traces", "spans"):
                    was_created = await _create_month_partition(
                        db, table_name, month_start
                    )
                    target = f"{table_name}_{suffix}"
                    if was_created:
                        created.append(target)
                    else:
                        skipped.append(target)

            await db.commit()
            log.info(
                "future_partitions_checked",
                created=created,
                skipped=skipped,
                lookahead_months=lookahead_months,
            )

        except Exception as e:
            await db.rollback()
            log.error("future_partition_check_failed", error=str(e))
            raise


@broker.task(schedule=[{"cron": "0 0 * * *"}])
async def run_data_retention() -> None:
    log.info("data_retention_started")

    async with get_db() as db:
        result = await db.execute(
            text("SELECT id, retention_days FROM projects WHERE is_active = true")
        )
        projects = result.mappings().all()

    for project in projects:
        cutoff = datetime.now(UTC) - timedelta(days=project["retention_days"])
        pid = str(project["id"])

        deleted_spans = 0
        deleted_traces = 0
        while True:
            async with get_db(project_id=pid) as db:
                batch = await _fetch_retention_batch(db, pid, cutoff)

            if not batch:
                break

            payload_keys = [
                row["payload_s3_key"] for row in batch if row.get("payload_s3_key")
            ]
            deleted_payload_keys = await _delete_s3_objects(pid, payload_keys)
            span_keys_to_delete = [
                {"id": row["id"], "started_at": row["started_at"]}
                for row in batch
                if not row.get("payload_s3_key")
                or row["payload_s3_key"] in deleted_payload_keys
                or not _is_project_payload_key(pid, str(row["payload_s3_key"]))
            ]

            async with get_db(project_id=pid) as db:
                deleted = await _delete_span_batch(db, pid, span_keys_to_delete)

            if deleted == 0:
                log.warning(
                    "retention_no_progress",
                    project_id=pid,
                    batch_size=len(batch),
                    payload_keys=len(payload_keys),
                )
                break

            deleted_spans += deleted

        async with get_db(project_id=pid) as db:
            deleted_traces = await _delete_stale_traces(db, pid, cutoff)

        log.info(
            "retention_done",
            project_id=pid,
            deleted_spans=deleted_spans,
            deleted_traces=deleted_traces,
        )
