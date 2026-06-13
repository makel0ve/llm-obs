from datetime import UTC, datetime

import structlog
from prometheus_client import Counter
from sqlalchemy import text

from app.core.db import get_db
from app.core.taskiq import dlq_broker

log = structlog.get_logger()
FAILED_TASKS_TOTAL = Counter(
    "llmobs_failed_tasks_total", "Tasks failed permanently", ["task_name"]
)


@dlq_broker.task
async def handle_failed_task(
    task_name: str, task_args: dict, error: str, attempts: int
) -> None:
    log.error(
        "task_failed_permanently", task=task_name, attempts=attempts, error=error[:500]
    )
    FAILED_TASKS_TOTAL.labels(task_name=task_name).inc()

    async with get_db() as db:
        try:
            await db.execute(
                text(
                    """
                INSERT INTO failed_tasks (task_name, task_args, error,
                    attempts, failed_at)
                VALUES (:task, :args, :error, :attempts, :now)
                """
                ),
                {
                    "task": task_name,
                    "args": str(task_args)[:10_000],
                    "error": error[:5_000],
                    "attempts": attempts,
                    "now": datetime.now(UTC),
                },
            )
            await db.commit()

        except Exception as e:
            log.critical("dlq_db_write_failed", task=task_name, error=str(e))
            await db.rollback()

            raise
