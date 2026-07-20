import json
import uuid
from dataclasses import dataclass
from typing import Any

from sqlalchemy import text

from app.core.db import get_db

OUTBOX_SPAN_INSERTED = "span.inserted"
OUTBOX_STATUS_PENDING = "PENDING"
OUTBOX_STATUS_DELIVERED = "DELIVERED"
OUTBOX_STATUS_FAILED = "FAILED"
OUTBOX_MAX_ATTEMPTS = 5


@dataclass(frozen=True)
class OutboxEventPayload:
    id: uuid.UUID
    project_id: uuid.UUID
    event_type: str
    event_key: str
    payload: dict[str, Any]
    attempts: int


def _normalize_payload(value: Any) -> dict[str, Any]:
    if isinstance(value, str):
        return dict(json.loads(value))
    return dict(value)


async def enqueue_outbox_event(
    *,
    db: Any,
    project_id: uuid.UUID,
    event_type: str,
    event_key: str,
    payload: dict[str, Any],
) -> None:
    await db.execute(
        text(
            """
            INSERT INTO outbox_events (
                id, project_id, event_type, event_key, payload, status
            )
            VALUES (
                :id, :project_id, :event_type, :event_key,
                CAST(:payload AS jsonb), 'PENDING'
            )
            ON CONFLICT (project_id, event_type, event_key) DO NOTHING
            """
        ),
        {
            "id": uuid.uuid4(),
            "project_id": project_id,
            "event_type": event_type,
            "event_key": event_key,
            "payload": json.dumps(payload),
        },
    )


class OutboxService:
    async def claim_pending(
        self, *, event_type: str, project_id: str | None = None, limit: int = 100
    ) -> list[OutboxEventPayload]:
        project_filter = ""
        params: dict[str, Any] = {
            "event_type": event_type,
            "limit": limit,
            "max_attempts": OUTBOX_MAX_ATTEMPTS,
        }
        if project_id is not None:
            project_filter = "AND project_id = :project_id"
            params["project_id"] = project_id

        async with get_db(project_id=project_id) as db:
            result = await db.execute(
                text(
                    f"""
                    WITH next_events AS (
                        SELECT id
                        FROM outbox_events
                        WHERE event_type = :event_type
                            AND status IN ('PENDING', 'FAILED')
                            AND attempts < :max_attempts
                            AND available_at <= TIMEZONE('utc', now())
                            {project_filter}
                        ORDER BY created_at ASC
                        LIMIT :limit
                        FOR UPDATE SKIP LOCKED
                    )
                    UPDATE outbox_events
                    SET status = 'PROCESSING',
                        attempts = attempts + 1,
                        locked_at = TIMEZONE('utc', now()),
                        updated_at = TIMEZONE('utc', now())
                    WHERE id IN (SELECT id FROM next_events)
                    RETURNING id, project_id, event_type, event_key, payload, attempts
                    """
                ),
                params,
            )
            rows = result.mappings().all()
            await db.commit()

        return [
            OutboxEventPayload(
                id=row["id"],
                project_id=row["project_id"],
                event_type=row["event_type"],
                event_key=row["event_key"],
                payload=_normalize_payload(row["payload"]),
                attempts=int(row["attempts"]),
            )
            for row in rows
        ]

    async def mark_delivered(self, event_id: uuid.UUID) -> None:
        async with get_db() as db:
            await db.execute(
                text(
                    """
                    UPDATE outbox_events
                    SET status = :status,
                        delivered_at = TIMEZONE('utc', now()),
                        locked_at = NULL,
                        last_error = NULL,
                        updated_at = TIMEZONE('utc', now())
                    WHERE id = :event_id
                    """
                ),
                {"event_id": event_id, "status": OUTBOX_STATUS_DELIVERED},
            )
            await db.commit()

    async def mark_failed(self, event_id: uuid.UUID, error: str) -> None:
        async with get_db() as db:
            await db.execute(
                text(
                    """
                    UPDATE outbox_events
                    SET status = CASE
                            WHEN attempts >= :max_attempts THEN :failed_status
                            ELSE :pending_status
                        END,
                        available_at = TIMEZONE('utc', now())
                            + make_interval(secs => LEAST(300, attempts * 10)),
                        locked_at = NULL,
                        last_error = :error,
                        updated_at = TIMEZONE('utc', now())
                    WHERE id = :event_id
                    """
                ),
                {
                    "event_id": event_id,
                    "error": error[:1000],
                    "max_attempts": OUTBOX_MAX_ATTEMPTS,
                    "pending_status": OUTBOX_STATUS_PENDING,
                    "failed_status": OUTBOX_STATUS_FAILED,
                },
            )
            await db.commit()
