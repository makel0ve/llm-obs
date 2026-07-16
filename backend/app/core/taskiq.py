from taskiq import SmartRetryMiddleware, TaskiqScheduler
from taskiq.schedule_sources import LabelScheduleSource
from taskiq_redis import ListQueueBroker, RedisAsyncResultBackend

from app.core.config import settings

queue_url = settings.effective_redis_queue_url

broker = (
    ListQueueBroker(queue_url)
    .with_result_backend(RedisAsyncResultBackend(queue_url))
    .with_middlewares(
        SmartRetryMiddleware(
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
