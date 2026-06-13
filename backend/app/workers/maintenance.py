from datetime import UTC, datetime, timedelta

import aioboto3
import structlog
from sqlalchemy import text

from app.core.config import settings
from app.core.db import get_db
from app.core.taskiq import broker

log = structlog.get_logger()


async def _delete_s3_objects(s3_keys: list[str]) -> None:
    try:
        session = aioboto3.Session()
        async with session.client(
            "s3",
            endpoint_url=settings.s3_endpoint_url,
            aws_access_key_id=settings.aws_access_key_id.get_secret_value(),
            aws_secret_access_key=settings.aws_secret_access_key.get_secret_value(),
        ) as s3:
            for i in range(0, len(s3_keys), 1000):
                batch = s3_keys[i : i + 1000]
                await s3.delete_objects(
                    Bucket=settings.s3_bucket,
                    Delete={
                        "Objects": [{"Key": k} for k in batch],
                        "Quiet": True,
                    },
                )

                log.info("s3_objects_deleted", count=len(batch))

    except Exception as e:
        log.error("s3_delete_failed", count=len(s3_keys), error=str(e))


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
                    CREATE TABLE IF NOT EXISTS spans_{suffix}
                    PARTITION OF spans
                    FOR VALUES FROM (:start_str) TO (:end_str)
                    """,
                ),
                {"start_str": str(start_str), "end_str": str(end_str)},
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
        pid = project["id"]

        async with get_db() as db:
            keys_result = await db.execute(
                text(
                    """
                SELECT payload_s3_key FROM spans
                WHERE project_id = :pid AND started_at < :cutoff
                    AND payload_s3_key IS NOT NULL
                LIMIT 10000
                """
                ),
                {"pid": pid, "cutoff": cutoff},
            )
            s3_keys = [r[0] for r in keys_result.fetchall()]

        if s3_keys:
            await _delete_s3_objects(s3_keys)

        total_deleted = 0
        while True:
            async with get_db() as db:
                result = await db.execute(
                    text(
                        """
                    DELETE FROM spans WHERE id IN (
                        SELECT id FROM spans
                        WHERE project_id = :pid AND started_at < :cutoff
                        LIMIT 1000
                    )
                    """
                    ),
                    {"pid": pid, "cutoff": cutoff},
                )
                await db.commit()
                deleted = result.rowcount if hasattr(result, "rowcount") else 0
                total_deleted += deleted
                if deleted == 0:
                    break

        log.info("retention_done", project_id=str(pid), deleted=total_deleted)
