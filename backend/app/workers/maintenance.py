from datetime import UTC, datetime, timedelta

import aioboto3
import structlog
from sqlalchemy import text

from app.core.config import settings
from app.core.db import get_db
from app.core.taskiq import broker

log = structlog.get_logger()
RETENTION_BATCH_SIZE = 1000
S3_DELETE_BATCH_SIZE = 1000


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
            SELECT id, payload_s3_key
            FROM spans
            WHERE project_id = :pid AND started_at < :cutoff
            ORDER BY started_at ASC
            LIMIT :limit
            """
        ),
        {"pid": project_id, "cutoff": cutoff, "limit": RETENTION_BATCH_SIZE},
    )
    return [dict(row) for row in result.mappings().all()]


async def _delete_span_batch(db, project_id: str, span_ids: list[str]) -> int:
    if not span_ids:
        return 0

    result = await db.execute(
        text(
            """
            DELETE FROM spans
            WHERE project_id = :pid AND id::text = ANY(:span_ids)
            """
        ),
        {"pid": project_id, "span_ids": span_ids},
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


@broker.task(schedule=[{"cron": "0 1 28 * *"}])
async def create_next_month_partition() -> None:
    now = datetime.now(UTC)
    if now.month == 12:
        y, m = now.year + 1, 1

    else:
        y, m = now.year, now.month + 1

    start_str = f"{y}-{m:02d}-01"
    if m == 12:
        end_str = f"{y + 1}-01-01"

    else:
        end_str = f"{y}-{m + 1:02d}-01"

    suffix = f"{y}_{m:02d}"

    async with get_db() as db:
        try:
            await db.execute(
                text(
                    f"""
                    CREATE TABLE IF NOT EXISTS traces_{suffix}
                    PARTITION OF traces
                    FOR VALUES FROM (:start_str) TO (:end_str)
                    """,
                ),
                {"start_str": str(start_str), "end_str": str(end_str)},
            )
            await db.execute(
                text(
                    f"""
                    ALTER TABLE traces_{suffix} ENABLE ROW LEVEL SECURITY
                    """,
                )
            )
            await db.execute(
                text(
                    f"""
                    ALTER TABLE traces_{suffix} FORCE ROW LEVEL SECURITY
                    """,
                )
            )
            await db.execute(
                text(
                    f"""
                    CREATE TABLE IF NOT EXISTS spans_{suffix}
                    PARTITION OF spans
                    FOR VALUES FROM (:start_str) TO (:end_str)
                    """,
                ),
                {"start_str": str(start_str), "end_str": str(end_str)},
            )
            await db.execute(
                text(
                    f"""
                    ALTER TABLE spans_{suffix} ENABLE ROW LEVEL SECURITY
                    """,
                )
            )
            await db.execute(
                text(
                    f"""
                    ALTER TABLE spans_{suffix} FORCE ROW LEVEL SECURITY
                    """,
                )
            )
            await db.commit()
            log.info(
                "partition_created", suffix=suffix, start_str=start_str, end_str=end_str
            )

        except Exception as e:
            await db.rollback()
            log.error("partition_creation_failed", suffix=suffix, error=str(e))
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
            span_ids_to_delete = [
                str(row["id"])
                for row in batch
                if not row.get("payload_s3_key")
                or row["payload_s3_key"] in deleted_payload_keys
                or not _is_project_payload_key(pid, str(row["payload_s3_key"]))
            ]

            async with get_db(project_id=pid) as db:
                deleted = await _delete_span_batch(db, pid, span_ids_to_delete)

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
