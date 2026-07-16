import json
import time
import uuid
from datetime import datetime
from typing import Any, TypedDict

import structlog
from dateutil.parser import parse as parse_dt
from sqlalchemy import text

from app.core.db import get_db
from app.core.metrics import (
    ingest_batch_processing_s,
    ingest_batches_failed,
    ingest_batches_processed,
    ingest_spans_dropped,
    spans_ingested,
)
from app.core.redis import get_redis
from app.core.taskiq import broker
from app.services.anomaly import AnomalyService
from app.services.cost import CostService
from app.services.ingest import BatchStatusService, bulk_insert_spans
from app.services.notifications import NotificationService
from app.services.storage import (
    DEFAULT_PAYLOAD_MAX_BYTES,
    DEFAULT_REDACT_KEYS,
    StorageService,
    parse_redact_keys,
    should_store_payload,
)

log = structlog.get_logger()


class PayloadPrivacySettings(TypedDict):
    payload_storage_mode: str
    payload_max_bytes: int
    payload_redact_keys: str


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

                    s3_key = None
                    if should_store_payload(
                        payload_mode, has_error=bool(span_data.get("error"))
                    ):
                        s3_key = await storage_svc.store_payload(
                            project_id=project_id,
                            span_id=span_data["span_id"],
                            messages=span_data.get("input_messages", []),
                            output=span_data.get("output"),
                            max_bytes=payload_max_bytes,
                            redact_keys=payload_redact_keys,
                        )

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
                            "payload_s3_key": s3_key,
                            "metadata": json.dumps(span_data.get("metadata", {})),
                        }
                    )

                except Exception as e:
                    failed_count += 1
                    ingest_spans_dropped.labels(reason="processing_error").inc()
                    log.error(
                        "span_processing_failed",
                        span_id=span_data.get("span_id"),
                        error=str(e),
                    )
                    continue

            await bulk_insert_spans(prepared_spans, db)

            trace_map: dict[Any, dict[str, Any]] = {}
            for span in prepared_spans:
                tid = span["trace_id"]
                if (
                    tid not in trace_map
                    or span["started_at"] < trace_map[tid]["started_at"]
                ):
                    trace_map[tid] = span

            for tid, span in trace_map.items():
                await db.execute(
                    text(
                        """
                    INSERT INTO traces (id, project_id, started_at, status, span_count,
                        total_tokens, total_cost_usd)
                    VALUES (:id, :project_id, :started_at, :status, 0, 0, 0)
                    ON CONFLICT (id, started_at) DO NOTHING
                    """
                    ),
                    {
                        "id": tid,
                        "project_id": span["project_id"],
                        "started_at": span["started_at"],
                        "status": span["status"],
                    },
                )

            await db.commit()

            for span_data in prepared_spans:
                spans_ingested.labels(
                    provider=span_data["provider"],
                    model=span_data["model"],
                    status=span_data["status"],
                ).inc()
                await redis.publish(
                    f"project:{project_id}:new_span",
                    json.dumps(
                        {
                            "span_id": str(span_data["id"]),
                            "name": span_data.get("name"),
                            "latency_ms": span_data["latency_ms"],
                            "status": span_data["status"],
                        }
                    ),
                )

        for trace_id, span in trace_map.items():
            await update_trace_aggregates.kiq(
                project_id=project_id,
                trace_id=str(trace_id),
                started_at=span["started_at"],
            )

        await check_batch_anomalies.kiq(project_id=project_id, spans=spans)
        await batch_status.mark_finished(
            project_id=project_id,
            batch_id=batch_id,
            processed=len(prepared_spans),
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
            WHERE project_id = :project_id AND is_active = true
            """
            ),
            {"project_id": project_id},
        )
        rules = result.mappings().all()

    if not rules:
        return

    for span in spans:
        anomalies = await anomaly_svc.check(project_id=project_id, span=span)

        for rule in rules:
            triggered = False
            value = span.get("latency_ms", 0)

            if rule["metric"] == "anomaly" and anomalies:
                triggered = True
            elif rule["metric"] == "latency_p95":
                if rule["condition"] == "gt" and value > float(rule["threshold"]):
                    triggered = True
                elif rule["condition"] == "lt" and value < float(rule["threshold"]):
                    triggered = True
            elif rule["metric"] == "error_rate":
                if "high_error_rate" in anomalies:
                    triggered = True
            elif rule["metric"] == "cost_hourly":
                value = float(span.get("cost_usd", 0))
                if rule["condition"] == "gt" and value > float(rule["threshold"]):
                    triggered = True

            if not triggered:
                continue

            message = (
                f"Alert '{rule['name']}' triggered for span `{span.get('name')}` "
                f"model=`{span.get('model')}` "
                f"latency={span.get('latency_ms')}ms "
                f"metric={rule['metric']} {rule['condition']} {rule['threshold']}"
            )

            sent = await notification_svc.send_alert(
                rule=dict(rule), value=value, message=message
            )
            if sent:
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

                log.info("alert_sent", rule=rule["name"], anomalies=anomalies)
