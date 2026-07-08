import json
import uuid
from datetime import UTC, datetime

import structlog
from fastapi import Depends
from redis.asyncio import Redis
from sqlalchemy import text

from app.core.metrics import ingest_batches_accepted, ingest_batches_failed
from app.core.redis import get_redis
from app.schemas.ingest import BatchStatusResponse, SpanSchema

log = structlog.get_logger()
IDEMPOTENCY_TTL = 86_400
BATCH_STATUS_TTL = 86_400


class BatchStatusService:
    def __init__(self, redis: Redis):
        self._redis = redis

    async def create_accepted(
        self, project_id: str, batch_id: str, accepted: int
    ) -> None:
        now = datetime.now(UTC).isoformat()
        await self._save(
            project_id=project_id,
            batch_id=batch_id,
            status={
                "batch_id": batch_id,
                "status": "accepted",
                "accepted": accepted,
                "processed": 0,
                "failed": 0,
                "error": None,
                "created_at": now,
                "updated_at": now,
            },
        )

    async def mark_processing(self, project_id: str, batch_id: str) -> None:
        await self._merge(
            project_id=project_id,
            batch_id=batch_id,
            updates={"status": "processing", "error": None},
        )

    async def mark_finished(
        self,
        project_id: str,
        batch_id: str,
        *,
        processed: int,
        failed: int,
    ) -> None:
        await self._merge(
            project_id=project_id,
            batch_id=batch_id,
            updates={
                "status": "partial_failed" if failed else "processed",
                "processed": processed,
                "failed": failed,
                "error": None,
            },
        )

    async def mark_failed(self, project_id: str, batch_id: str, error: str) -> None:
        await self._merge(
            project_id=project_id,
            batch_id=batch_id,
            updates={"status": "failed", "error": error[:1000]},
        )

    async def get(self, project_id: str, batch_id: str) -> BatchStatusResponse | None:
        value = await self._redis.get(self._key(project_id, batch_id))
        if not value:
            return None

        return BatchStatusResponse(**json.loads(value))

    async def _merge(self, project_id: str, batch_id: str, updates: dict) -> None:
        key = self._key(project_id, batch_id)
        existing = await self._redis.get(key)
        now = datetime.now(UTC).isoformat()

        if existing:
            status = json.loads(existing)
        else:
            status = {
                "batch_id": batch_id,
                "accepted": 0,
                "processed": 0,
                "failed": 0,
                "error": None,
                "created_at": now,
            }

        status.update(updates)
        status["updated_at"] = now
        await self._save(project_id=project_id, batch_id=batch_id, status=status)

    async def _save(self, project_id: str, batch_id: str, status: dict) -> None:
        await self._redis.setex(
            self._key(project_id, batch_id),
            BATCH_STATUS_TTL,
            json.dumps(status),
        )

    def _key(self, project_id: str, batch_id: str) -> str:
        return f"ingest_batch:{project_id}:{batch_id}"


class IngestService:
    def __init__(self, redis: Redis):
        self._redis = redis
        self._batch_status = BatchStatusService(redis=redis)

    async def accept_batch(self, project_id: str, spans: list[SpanSchema]) -> str:
        batch_id = str(uuid.uuid4())
        from app.workers.process_span import process_span_batch

        await self._batch_status.create_accepted(
            project_id=project_id, batch_id=batch_id, accepted=len(spans)
        )
        try:
            await process_span_batch.kiq(
                batch_id=batch_id,
                project_id=project_id,
                spans=[s.model_dump(mode="json") for s in spans],
            )
        except Exception as e:
            await self._batch_status.mark_failed(
                project_id=project_id, batch_id=batch_id, error=str(e)
            )
            ingest_batches_failed.labels(stage="enqueue").inc()
            raise

        ingest_batches_accepted.inc()
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

    async def get_batch_status(
        self, project_id: str, batch_id: str
    ) -> BatchStatusResponse | None:
        return await self._batch_status.get(project_id=project_id, batch_id=batch_id)


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
