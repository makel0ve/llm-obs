import json
import uuid

import structlog
from fastapi import Depends
from redis.asyncio import Redis
from sqlalchemy import text

from app.core.redis import get_redis
from app.schemas.ingest import SpanSchema

log = structlog.get_logger()
IDEMPOTENCY_TTL = 86_400


class IngestService:
    def __init__(self, redis: Redis):
        self._redis = redis

    async def accept_batch(self, project_id: str, spans: list[SpanSchema]) -> str:
        batch_id = str(uuid.uuid4())
        from app.workers.process_span import process_span_batch

        await process_span_batch.kiq(
            batch_id=batch_id,
            project_id=project_id,
            spans=[s.model_dump(mode="json") for s in spans],
        )

        log.info("batch_accepted", batch_id=batch_id, span_count=len(spans))
        return batch_id

    async def get_idempotency_result(self, project_id: str, key: str) -> dict | None:
        redis_key = f"idempotency:{project_id}:{key}"
        existing = await self._redis.get(redis_key)
        return json.loads(existing) if existing else None

    async def save_idempotency_result(
        self, project_id: str, key: str, result: dict
    ) -> None:
        redis_key = f"idempotency:{project_id}:{key}"
        await self._redis.setex(redis_key, IDEMPOTENCY_TTL, json.dumps(result))


def get_ingest_service(redis: Redis = Depends(get_redis)) -> IngestService:
    return IngestService(redis=redis)


async def bulk_insert_spans(spans: list[dict], db) -> int:
    if not spans:
        return 0

    await db.execute(
        text(
            """
        INSERT INTO spans (id, trace_id, project_id, name, provider, model,
            input_tokens, output_tokens, cost_usd, latency_ms, status, error,
            started_at, payload_s3_key, metadata)
        VALUES (:id, :trace_id, :project_id, :name, :provider, :model,
            :input_tokens, :output_tokens, :cost_usd, :latency_ms, :status, :error,
            :started_at, :payload_s3_key, :metadata)
        ON CONFLICT (id, started_at) DO NOTHING
        """
        ),
        spans,
    )
    await db.commit()

    return len(spans)
