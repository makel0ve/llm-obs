import json
import time
import uuid
from collections import Counter
from datetime import UTC, datetime
from decimal import Decimal, InvalidOperation
from typing import Any, TypedDict, cast

import structlog
from botocore.exceptions import BotoCoreError, ClientError
from dateutil.parser import ParserError
from dateutil.parser import parse as parse_dt
from redis.exceptions import RedisError
from sqlalchemy import text
from sqlalchemy.exc import SQLAlchemyError

from app.core.db import get_db
from app.core.metrics import (
    ingest_batch_accepted_to_finished_s,
    ingest_batch_accepted_to_processing_s,
    ingest_batch_processing_s,
    ingest_batches_failed,
    ingest_batches_processed,
    ingest_span_processing_failures,
    ingest_span_source_to_accepted_s,
    ingest_span_source_to_processed_s,
    ingest_spans_dropped,
    outbox_delivery_attempts,
    payload_storage_results,
    spans_ingested,
)
from app.core.redis import get_redis
from app.core.taskiq import broker
from app.services.anomaly import AnomalyService
from app.services.cost import CostService
from app.services.ingest import BatchStatusService, SpanIdentity, bulk_insert_spans
from app.services.notifications import NotificationService
from app.services.outbox import (
    OUTBOX_SPAN_INSERTED,
    OutboxService,
    enqueue_outbox_event,
)
from app.services.span_metric_buckets import (
    query_bucketed_alert_value,
    update_span_metric_buckets,
)
from app.services.storage import (
    DEFAULT_PAYLOAD_MAX_BYTES,
    DEFAULT_REDACT_KEYS,
    PayloadStorageResult,
    StorageService,
    parse_redact_keys,
    redact_payload,
    should_store_payload,
)

log = structlog.get_logger()

WINDOWED_ALERT_METRICS = frozenset({"latency_p95", "error_rate", "cost_hourly"})
TRANSIENT_SPAN_ERRORS = (
    SQLAlchemyError,
    RedisError,
    BotoCoreError,
    ClientError,
    TimeoutError,
    ConnectionError,
)
PAYLOAD_LIKE_METADATA_KEYS = frozenset(
    {
        "messages",
        "input_messages",
        "input",
        "output",
        "prompt",
        "system",
        "system_prompt",
    }
)
SENSITIVE_METADATA_KEY_PARTS = frozenset(
    {
        "api_key",
        "authorization",
        "cookie",
        "password",
        "secret",
        "token",
    }
)
SAFE_SPAN_METADATA_KEYS = frozenset(
    {
        "route",
        "source",
        "stream",
        "stream_complete",
    }
)


class PayloadPrivacySettings(TypedDict):
    payload_storage_mode: str
    payload_max_bytes: int
    payload_redact_keys: str


def skipped_payload_result(payload_mode: str) -> PayloadStorageResult:
    if payload_mode == "none":
        return PayloadStorageResult(
            s3_key=None, status="omitted", drop_reason="storage_mode_none"
        )

    return PayloadStorageResult(
        s3_key=None, status="omitted", drop_reason="errors_only_non_error"
    )


def sanitize_span_metadata(
    metadata: dict[str, Any], redact_keys: set[str]
) -> dict[str, Any]:
    redacted = redact_payload(metadata, redact_keys)
    if not isinstance(redacted, dict):
        return {}

    sanitized: dict[str, Any] = {}
    for key, value in redacted.items():
        key_text = str(key)
        key_lower = key_text.lower()
        if key_lower in PAYLOAD_LIKE_METADATA_KEYS:
            continue
        if any(part in key_lower for part in SENSITIVE_METADATA_KEY_PARTS):
            continue
        if key_lower not in SAFE_SPAN_METADATA_KEYS:
            continue
        if not isinstance(value, str | int | float | bool) and value is not None:
            continue

        sanitized[key_text] = value

    return sanitized


def select_inserted_spans(
    prepared_spans: list[dict[str, Any]], inserted_identities: list[SpanIdentity]
) -> list[dict[str, Any]]:
    remaining = Counter(inserted_identities)
    inserted_spans: list[dict[str, Any]] = []

    for span in prepared_spans:
        identity = (span["id"], span["started_at"])
        if remaining[identity] <= 0:
            continue

        inserted_spans.append(span)
        remaining[identity] -= 1

    return inserted_spans


def is_transient_span_processing_error(exc: Exception) -> bool:
    return isinstance(exc, TRANSIENT_SPAN_ERRORS)


async def load_payload_privacy_settings(
    db: Any, project_id: str
) -> PayloadPrivacySettings:
    result = await db.execute(
        text(
            """
            SELECT payload_storage_mode, payload_max_bytes, payload_redact_keys
            FROM projects
            WHERE id = :project_id
            """
        ),
        {"project_id": project_id},
    )
    row = result.mappings().one_or_none()
    if not row:
        return {
            "payload_storage_mode": "all",
            "payload_max_bytes": DEFAULT_PAYLOAD_MAX_BYTES,
            "payload_redact_keys": DEFAULT_REDACT_KEYS,
        }

    return {
        "payload_storage_mode": row["payload_storage_mode"] or "all",
        "payload_max_bytes": row["payload_max_bytes"] or DEFAULT_PAYLOAD_MAX_BYTES,
        "payload_redact_keys": row["payload_redact_keys"] or DEFAULT_REDACT_KEYS,
    }


@broker.task(retry_on_error=True, max_retries=3)
async def process_span_batch(
    batch_id: str, project_id: str, spans: list[dict[str, Any]]
) -> None:
    log.info("processing_batch", batch_id=batch_id, count=len(spans))
    started_at_monotonic = time.perf_counter()
    cost_svc = CostService()
    storage_svc = StorageService()
    redis = await get_redis()
    batch_status = BatchStatusService(redis=redis)
    accepted_status = await batch_status.get(project_id=project_id, batch_id=batch_id)
    accepted_at = accepted_status.created_at if accepted_status is not None else None
    processing_started_at = datetime.now(UTC)
    observe_duration(
        ingest_batch_accepted_to_processing_s,
        accepted_at,
        processing_started_at,
    )
    await batch_status.mark_processing(project_id=project_id, batch_id=batch_id)

    try:
        async with get_db(project_id=project_id) as db:
            payload_settings = await load_payload_privacy_settings(db, project_id)
            payload_mode = str(payload_settings["payload_storage_mode"])
            payload_max_bytes = int(payload_settings["payload_max_bytes"])
            payload_redact_keys = parse_redact_keys(
                str(payload_settings["payload_redact_keys"])
            )
            prepared_spans: list[dict[str, Any]] = []
            failed_count = 0
            for span_data in spans:
                try:
                    started_at = (
                        parse_dt(span_data["started_at"])
                        if isinstance(span_data["started_at"], str)
                        else span_data["started_at"]
                    )

                    cost = await cost_svc.calculate(
                        provider=span_data["provider"],
                        model=span_data["model"],
                        input_tokens=span_data["input_tokens"],
                        output_tokens=span_data["output_tokens"],
                        at_time=started_at,
                    )

                    if should_store_payload(
                        payload_mode, has_error=bool(span_data.get("error"))
                    ):
                        payload_result = await storage_svc.store_payload(
                            project_id=project_id,
                            span_id=span_data["span_id"],
                            messages=span_data.get("input_messages", []),
                            output=span_data.get("output"),
                            max_bytes=payload_max_bytes,
                            redact_keys=payload_redact_keys,
                        )
                    else:
                        payload_result = skipped_payload_result(payload_mode)

                    payload_storage_results.labels(
                        status=payload_result.status,
                        reason=payload_result.drop_reason or "none",
                    ).inc()
                    prepared_spans.append(
                        {
                            "id": uuid.UUID(span_data["span_id"]),
                            "trace_id": uuid.UUID(span_data["trace_id"]),
                            "project_id": uuid.UUID(project_id),
                            "parent_span_id": uuid.UUID(span_data["parent_span_id"])
                            if span_data.get("parent_span_id")
                            else None,
                            "name": span_data.get("name", "llm_call"),
                            "provider": span_data["provider"],
                            "model": span_data["model"],
                            "input_tokens": span_data["input_tokens"],
                            "output_tokens": span_data["output_tokens"],
                            "cost_usd": cost,
                            "latency_ms": span_data["latency_ms"],
                            "status": "error" if span_data.get("error") else "ok",
                            "error": span_data.get("error"),
                            "started_at": started_at,
                            "payload_s3_key": payload_result.s3_key,
                            "payload_status": payload_result.status,
                            "payload_drop_reason": payload_result.drop_reason,
                            "metadata": json.dumps(
                                sanitize_span_metadata(
                                    span_data.get("metadata", {}),
                                    payload_redact_keys,
                                )
                            ),
                        }
                    )

                except Exception as e:
                    if is_transient_span_processing_error(e):
                        log.warning(
                            "span_processing_transient_failed",
                            span_id=span_data.get("span_id"),
                            error=str(e),
                        )
                        raise

                    failed_count += 1
                    failure_reason = classify_span_processing_failure(e)
                    ingest_span_processing_failures.labels(reason=failure_reason).inc()
                    ingest_spans_dropped.labels(reason="processing_error").inc()
                    log.error(
                        "span_processing_failed",
                        span_id=span_data.get("span_id"),
                        reason=failure_reason,
                        error=str(e),
                    )
                    continue

            inserted_identities = await bulk_insert_spans(prepared_spans, db)
            inserted_spans = select_inserted_spans(
                prepared_spans=prepared_spans,
                inserted_identities=inserted_identities,
            )

            trace_map: dict[Any, dict[str, Any]] = {}
            for span in inserted_spans:
                tid = span["trace_id"]
                if (
                    tid not in trace_map
                    or span["started_at"] < trace_map[tid]["started_at"]
                ):
                    trace_map[tid] = span

            stable_trace_starts: dict[Any, datetime] = {}
            for tid, span in trace_map.items():
                stable_trace_starts[tid] = await ensure_trace_row(
                    db=db,
                    project_id=uuid.UUID(project_id),
                    trace_id=tid,
                    started_at=span["started_at"],
                    status=span["status"],
                )

            for span_data in inserted_spans:
                await enqueue_outbox_event(
                    db=db,
                    project_id=uuid.UUID(project_id),
                    event_type=OUTBOX_SPAN_INSERTED,
                    event_key=str(span_data["id"]),
                    payload={
                        "span_id": str(span_data["id"]),
                        "name": span_data.get("name"),
                        "latency_ms": span_data["latency_ms"],
                        "status": span_data["status"],
                    },
                )

            await update_span_metric_buckets(
                db=db, project_id=project_id, spans=inserted_spans
            )
            await db.commit()

            for span_data in inserted_spans:
                spans_ingested.labels(
                    provider=span_data["provider"],
                    model=span_data["model"],
                    status=span_data["status"],
                ).inc()

        if inserted_spans:
            try:
                await deliver_span_outbox_events.kiq(project_id=project_id)
            except Exception as e:
                log.warning(
                    "outbox_delivery_enqueue_failed",
                    project_id=project_id,
                    batch_id=batch_id,
                    error=str(e),
                )

        for trace_id, span in trace_map.items():
            await update_trace_aggregates.kiq(
                project_id=project_id,
                trace_id=str(trace_id),
                started_at=stable_trace_starts[trace_id].isoformat(),
            )

        await check_batch_anomalies.kiq(project_id=project_id, spans=spans)
        processed_at = datetime.now(UTC)
        observe_inserted_span_lag(
            spans=inserted_spans,
            accepted_at=accepted_at,
            processed_at=processed_at,
        )
        observe_duration(
            ingest_batch_accepted_to_finished_s,
            accepted_at,
            processed_at,
        )
        await batch_status.mark_finished(
            project_id=project_id,
            batch_id=batch_id,
            processed=len(inserted_spans),
            failed=failed_count,
        )
        processing_status = "partial_failed" if failed_count else "processed"
        ingest_batches_processed.labels(status=processing_status).inc()
        ingest_batch_processing_s.observe(time.perf_counter() - started_at_monotonic)
        log.info("batch_processed", batch_id=batch_id)

    except Exception as e:
        await batch_status.mark_failed(
            project_id=project_id, batch_id=batch_id, error=str(e)
        )
        ingest_batches_failed.labels(stage="worker").inc()
        ingest_batch_processing_s.observe(time.perf_counter() - started_at_monotonic)
        raise


def observe_inserted_span_lag(
    spans: list[dict[str, Any]],
    accepted_at: datetime | None,
    processed_at: datetime,
) -> None:
    for span in spans:
        started_at = span.get("started_at")
        if not isinstance(started_at, datetime):
            continue

        observe_duration(ingest_span_source_to_accepted_s, started_at, accepted_at)
        observe_duration(ingest_span_source_to_processed_s, started_at, processed_at)


def observe_duration(
    metric: Any, started_at: datetime | None, ended_at: datetime | None
) -> None:
    if started_at is None or ended_at is None:
        return

    seconds = (ended_at - started_at).total_seconds()
    metric.observe(max(seconds, 0.0))


def classify_span_processing_failure(exc: Exception) -> str:
    if isinstance(exc, ParserError):
        return "invalid_timestamp"
    if isinstance(exc, KeyError):
        return "missing_required_field"
    if isinstance(exc, InvalidOperation):
        return "invalid_numeric_field"
    if isinstance(exc, TypeError | ValueError):
        return "invalid_field"

    return "processing_error"


async def ensure_trace_row(
    db: Any,
    project_id: uuid.UUID,
    trace_id: uuid.UUID,
    started_at: datetime,
    status: str,
) -> datetime:
    result = await db.execute(
        text(
            """
            SELECT started_at
            FROM traces
            WHERE project_id = :project_id AND id = :trace_id
            ORDER BY started_at ASC
            LIMIT 1
            """
        ),
        {"project_id": project_id, "trace_id": trace_id},
    )
    row = result.mappings().one_or_none()
    existing_started_at_raw = row.get("started_at") if row is not None else None
    if existing_started_at_raw is None:
        await db.execute(
            text(
                """
                INSERT INTO traces (
                    id, project_id, started_at, status, span_count,
                    total_tokens, total_cost_usd
                )
                VALUES (:id, :project_id, :started_at, :status, 0, 0, 0)
                ON CONFLICT (id, started_at) DO NOTHING
                """
            ),
            {
                "id": trace_id,
                "project_id": project_id,
                "started_at": started_at,
                "status": status,
            },
        )
        return started_at

    existing_started_at = cast(datetime, existing_started_at_raw)
    if existing_started_at <= started_at:
        return existing_started_at

    await db.execute(
        text(
            """
            UPDATE traces
            SET started_at = :started_at
            WHERE project_id = :project_id
                AND id = :trace_id
                AND started_at = :existing_started_at
            """
        ),
        {
            "project_id": project_id,
            "trace_id": trace_id,
            "started_at": started_at,
            "existing_started_at": existing_started_at,
        },
    )
    return started_at


@broker.task(retry_on_error=True, max_retries=3, schedule=[{"cron": "* * * * *"}])
async def deliver_span_outbox_events(
    project_id: str | None = None, limit: int = 100
) -> None:
    outbox = OutboxService()
    events = await outbox.claim_pending(
        event_type=OUTBOX_SPAN_INSERTED, project_id=project_id, limit=limit
    )
    if not events:
        return

    redis = await get_redis()
    for event in events:
        try:
            await redis.publish(
                f"project:{event.project_id}:new_span",
                json.dumps(event.payload),
            )
        except Exception as e:
            await outbox.mark_failed(event.id, str(e))
            outbox_delivery_attempts.labels(
                event_type=event.event_type,
                result="failed",
            ).inc()
            raise

        await outbox.mark_delivered(event.id)
        outbox_delivery_attempts.labels(
            event_type=event.event_type,
            result="delivered",
        ).inc()


@broker.task
async def update_trace_aggregates(
    project_id: str, trace_id: str, started_at: str
) -> None:
    if isinstance(started_at, str):
        sat_dt = datetime.fromisoformat(started_at.replace("Z", "+00:00"))

    else:
        sat_dt = started_at

    async with get_db(project_id=project_id) as db:
        await db.execute(
            text(
                """
            UPDATE traces SET
                total_cost_usd = (SELECT COALESCE(SUM(cost_usd), 0)
                                    FROM spans
                                    WHERE project_id = :pid
                                        AND trace_id = :tid AND started_at >= :sat),
                total_tokens   = (SELECT COALESCE(SUM(input_tokens + output_tokens), 0)
                                    FROM spans
                                    WHERE project_id = :pid
                                        AND trace_id = :tid AND started_at >= :sat),
                span_count     = (SELECT COUNT(*)
                                    FROM spans
                                    WHERE project_id = :pid
                                        AND trace_id = :tid AND started_at >= :sat),
                ended_at       = (SELECT MAX(
                                        started_at
                                        + make_interval(secs => latency_ms / 1000.0)
                                    )
                                    FROM spans
                                    WHERE project_id = :pid
                                        AND trace_id = :tid AND started_at >= :sat),
                status = CASE WHEN EXISTS(
                    SELECT 1 FROM spans
                    WHERE project_id = :pid
                        AND trace_id = :tid AND started_at >= :sat AND status = 'error'
                ) THEN 'error' ELSE 'ok' END
            WHERE project_id = :pid AND id = :tid AND started_at = :sat
            """
            ),
            {"pid": project_id, "tid": trace_id, "sat": sat_dt},
        )

        await db.commit()


@broker.task
async def check_batch_anomalies(project_id: str, spans: list[dict[str, Any]]) -> None:
    anomaly_svc = AnomalyService()
    notification_svc = NotificationService()

    async with get_db() as db:
        result = await db.execute(
            text(
                """
            SELECT id, name, metric, condition, threshold,
                cooldown_minutes, notify_slack_webhook, notify_email
            FROM alert_rules
            WHERE project_id = :project_id
                AND is_active = true
                AND metric = 'anomaly'
            """
            ),
            {"project_id": project_id},
        )
        rules = result.mappings().all()

    if not rules:
        return

    for rule in rules:
        for span in spans:
            anomalies = await anomaly_svc.check(project_id=project_id, span=span)
            if not anomalies:
                continue

            value = float(span.get("latency_ms", 0))
            message = (
                f"Alert '{rule['name']}' triggered for span `{span.get('name')}` "
                f"model=`{span.get('model')}` latency={span.get('latency_ms')}ms "
                f"metric={rule['metric']} condition={rule['condition']}"
            )
            await record_alert_if_sent(
                notification_svc=notification_svc,
                rule=rule,
                value=value,
                message=message,
            )


@broker.task(schedule=[{"cron": "* * * * *"}])
async def evaluate_scheduled_alert_rules() -> None:
    notification_svc = NotificationService()

    async with get_db() as db:
        result = await db.execute(
            text(
                """
            SELECT id, project_id, name, metric, condition, threshold,
                window_minutes, cooldown_minutes, notify_slack_webhook, notify_email
            FROM alert_rules
            WHERE is_active = true
                AND metric IN ('latency_p95', 'error_rate', 'cost_hourly')
            """
            ),
            {},
        )
        rules = result.mappings().all()

    for rule in rules:
        if await notification_svc.is_on_cooldown(rule["id"]):
            log.debug(
                "scheduled_alert_suppressed_cooldown",
                rule_id=str(rule["id"]),
                project_id=str(rule["project_id"]),
            )
            continue

        project_id = str(rule["project_id"])
        async with get_db(project_id=project_id) as db:
            triggered, value = await evaluate_windowed_alert_rule(
                db=db, project_id=project_id, rule=rule
            )

        if not triggered:
            continue

        message = (
            f"Alert '{rule['name']}' triggered for project `{project_id}` "
            f"metric={rule['metric']} {rule['condition']} {rule['threshold']} "
            f"value={value} window={rule['window_minutes']}m"
        )
        await record_alert_if_sent(
            notification_svc=notification_svc,
            rule=rule,
            value=value,
            message=message,
        )


async def evaluate_windowed_alert_rule(
    db: Any, project_id: str, rule: Any
) -> tuple[bool, float]:
    threshold = _rule_threshold(rule)
    if threshold is None:
        return False, 0.0

    metric = str(rule["metric"])
    if metric == "latency_p95":
        value, sample_count = await _query_alert_value(
            db=db,
            sql="""
                SELECT
                    COALESCE(
                        percentile_cont(0.95) WITHIN GROUP (ORDER BY latency_ms),
                        0
                    ) AS value,
                    COUNT(*) AS sample_count
                FROM spans
                WHERE project_id = :project_id
                    AND started_at >= NOW() - make_interval(mins => :window_minutes)
            """,
            project_id=project_id,
            window_minutes=int(rule["window_minutes"]),
        )
    elif metric == "error_rate":
        value, sample_count = await query_bucketed_alert_value(
            db=db,
            project_id=project_id,
            metric=metric,
            window_minutes=int(rule["window_minutes"]),
        )
    elif metric == "cost_hourly":
        value, sample_count = await query_bucketed_alert_value(
            db=db,
            project_id=project_id,
            metric=metric,
            window_minutes=int(rule["window_minutes"]),
        )
    else:
        return False, 0.0

    if sample_count <= 0:
        return False, value

    return _condition_matches(str(rule["condition"]), value, threshold), value


async def _query_alert_value(
    db: Any, sql: str, project_id: str, window_minutes: int
) -> tuple[float, int]:
    result = await db.execute(
        text(sql),
        {"project_id": project_id, "window_minutes": window_minutes},
    )
    row = result.mappings().one()

    return _to_float(row["value"]), int(row["sample_count"] or 0)


def _rule_threshold(rule: Any) -> float | None:
    threshold = rule["threshold"]
    if threshold is None:
        return None

    return _to_float(threshold)


def _to_float(value: Any) -> float:
    if isinstance(value, Decimal):
        return float(value)

    return float(value or 0)


def _condition_matches(condition: str, value: float, threshold: float) -> bool:
    if condition == "gt":
        return value > threshold
    if condition == "lt":
        return value < threshold

    return False


async def record_alert_if_sent(
    notification_svc: NotificationService, rule: Any, value: float, message: str
) -> None:
    sent = await notification_svc.send_alert(
        rule=dict(rule), value=value, message=message
    )
    if not sent:
        return

    async with get_db() as db:
        await db.execute(
            text(
                """
                INSERT INTO alert_events (id, rule_id, value, message)
                VALUES (:id, :rule_id, :value, :message)
                """
            ),
            {
                "id": str(uuid.uuid4()),
                "rule_id": str(rule["id"]),
                "value": value,
                "message": message,
            },
        )
        await db.commit()

    log.info("alert_sent", rule=rule["name"], metric=rule["metric"])
