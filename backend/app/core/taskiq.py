from typing import Any

import structlog
from taskiq import SmartRetryMiddleware, TaskiqScheduler
from taskiq.exceptions import NoResultError
from taskiq.message import TaskiqMessage
from taskiq.result import TaskiqResult
from taskiq.schedule_sources import LabelScheduleSource
from taskiq_redis import ListQueueBroker, RedisAsyncResultBackend

from app.core.config import settings
from app.services.failed_tasks import summarize_task_args

log = structlog.get_logger()


def _task_args_for_dlq(message: TaskiqMessage) -> dict[str, Any]:
    if message.kwargs:
        raw_args = dict(message.kwargs)
    elif message.task_name.endswith(":process_span_batch"):
        raw_args = {
            key: value
            for key, value in zip(("batch_id", "project_id", "spans"), message.args)
        }
    else:
        raw_args = {f"arg_{index}": value for index, value in enumerate(message.args)}

    return summarize_task_args(raw_args)


class DLQRetryMiddleware(SmartRetryMiddleware):
    async def on_error(
        self,
        message: TaskiqMessage,
        result: TaskiqResult[Any],
        exception: BaseException,
    ) -> None:
        capture_final_failure = True
        if self.types_of_exceptions is not None and not isinstance(
            exception,
            tuple(self.types_of_exceptions),
        ):
            capture_final_failure = False
        elif isinstance(exception, NoResultError):
            capture_final_failure = False
        elif not self.is_retry_on_error(message):
            capture_final_failure = False
        else:
            retries = int(message.labels.get("_retries", 0)) + 1
            max_retries = int(
                message.labels.get("max_retries", self.default_retry_count)
            )
            capture_final_failure = retries >= max_retries

        await super().on_error(message, result, exception)

        if not capture_final_failure:
            return

        try:
            from app.workers.dlq import handle_failed_task

            await handle_failed_task.kiq(
                task_name=message.task_name,
                task_args=_task_args_for_dlq(message),
                error=str(exception),
                attempts=int(message.labels.get("_retries", 0)) + 1,
            )
        except Exception as dlq_error:
            log.critical(
                "dlq_enqueue_failed",
                task=message.task_name,
                error=str(dlq_error),
            )


queue_url = settings.effective_redis_queue_url

broker = (
    ListQueueBroker(queue_url)
    .with_result_backend(RedisAsyncResultBackend(queue_url))
    .with_middlewares(
        DLQRetryMiddleware(
            default_retry_count=3,
            default_delay=1,
            use_jitter=True,
            use_delay_exponent=True,
            max_delay_exponent=30,
        )
    )
)

scheduler = TaskiqScheduler(broker=broker, sources=[LabelScheduleSource(broker)])

dlq_broker = ListQueueBroker(queue_url, queue_name="llm-obs-dlq")
