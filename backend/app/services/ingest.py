import hashlib
import json
import uuid
from datetime import UTC, datetime
from typing import Any, cast

import structlog
from fastapi import Depends
from redis.asyncio import Redis
from sqlalchemy.dialects.postgresql import insert

from app.core.metrics import ingest_batches_accepted, ingest_batches_failed
from app.core.redis import get_redis
from app.models.span import Span
from app.schemas.ingest import BatchStatusResponse, SpanSchema

log = structlog.get_logger()
IDEMPOTENCY_TTL = 86_400
BATCH_STATUS_TTL = 86_400
SpanIdentity = tuple[Any, datetime]


class IdempotencyConflictError(Exception):
    pass


def ingest_request_hash(spans: list[SpanSchema]) -> str:
    payload = [span.model_dump(mode="json") for span in spans]
    canonical = json.dumps(payload, sort_keys=True, separators=(",", ":"))
    return hashlib.sha256(canonical.encode("utf-8")).hexdigest()


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

    async def new_batch_id(self) -> str:
        return str(uuid.uuid4())

    async def accept_batch(
        self, project_id: str, spans: list[SpanSchema], batch_id: str | None = None
    ) -> str:
        batch_id = batch_id or await self.new_batch_id()
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

    async def reserve_idempotency_result(
        self, project_id: str, key: str, request_hash: str, result: dict[str, Any]
    ) -> dict[str, Any] | None:
        redis_key = f"idempotency:{project_id}:{key}"
        record = {"request_hash": request_hash, "result": result}
        reserved = await self._redis.set(
            redis_key,
            json.dumps(record),
            ex=IDEMPOTENCY_TTL,
            nx=True,
        )
        if reserved:
            return None

        existing = await self._redis.get(redis_key)
        if not existing:
            return None

        existing_record = json.loads(existing)
        if existing_record.get("request_hash") != request_hash:
            raise IdempotencyConflictError

        return existing_record.get("result")

    async def release_idempotency_result(self, project_id: str, key: str) -> None:
        redis_key = f"idempotency:{project_id}:{key}"
        await self._redis.delete(redis_key)

    async def get_batch_status(
        self, project_id: str, batch_id: str
    ) -> BatchStatusResponse | None:
        return await self._batch_status.get(project_id=project_id, batch_id=batch_id)


def get_ingest_service(redis: Redis = Depends(get_redis)) -> IngestService:
    return IngestService(redis=redis)


async def bulk_insert_spans(spans: list[dict], db) -> list[SpanIdentity]:
    if not spans:
        return []

    span_table = cast(Any, Span.__table__)
    stmt = (
        insert(span_table)
        .values(spans)
        .on_conflict_do_nothing(index_elements=["id", "started_at"])
        .returning(span_table.c.id, span_table.c.started_at)
    )
    result = await db.execute(stmt)

    return [(row.id, row.started_at) for row in result.all()]
