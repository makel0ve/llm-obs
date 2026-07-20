from datetime import UTC, datetime
from typing import Any

import structlog

from app.core.db import get_db
from app.core.metrics import failed_tasks
from app.core.taskiq import dlq_broker
from app.services.failed_tasks import record_failed_task

log = structlog.get_logger()


@dlq_broker.task
async def handle_failed_task(
    task_name: str, task_args: dict[str, Any], error: str, attempts: int
) -> None:
    log.error(
        "task_failed_permanently", task=task_name, attempts=attempts, error=error[:500]
    )
    failed_tasks.labels(task_name=task_name).inc()

    async with get_db() as db:
        try:
            await record_failed_task(
                db,
                task_name=task_name,
                task_args=task_args,
                error=error,
                attempts=attempts,
                failed_at=datetime.now(UTC),
            )
            await db.commit()

        except Exception as e:
            log.critical("dlq_db_write_failed", task=task_name, error=str(e))
            await db.rollback()

            raise
