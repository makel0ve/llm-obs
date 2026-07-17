import base64
import binascii
import json
from datetime import datetime
from typing import Any

from sqlalchemy import text

from app.core.db import get_db


def encode_trace_cursor(started_at: datetime, trace_id: str) -> str:
    payload = {
        "started_at": started_at.isoformat(),
        "id": trace_id,
    }
    raw = json.dumps(payload, separators=(",", ":")).encode()

    return base64.urlsafe_b64encode(raw).decode()


def decode_trace_cursor(cursor: str) -> tuple[datetime, str]:
    try:
        raw = base64.urlsafe_b64decode(cursor.encode()).decode()
    except (binascii.Error, UnicodeDecodeError) as exc:
        raise ValueError("Invalid pagination cursor") from exc

    try:
        payload = json.loads(raw)
        cursor_dt = datetime.fromisoformat(payload["started_at"])
        cursor_id = str(payload["id"])
    except (KeyError, TypeError, ValueError, json.JSONDecodeError):
        cursor_dt, cursor_id = _decode_legacy_trace_cursor(raw)

    if not cursor_id:
        raise ValueError("Invalid pagination cursor")

    return cursor_dt, cursor_id


def _decode_legacy_trace_cursor(raw: str) -> tuple[datetime, str]:
    try:
        dt_str, cursor_id = raw.rsplit(":", 1)
        return datetime.fromisoformat(dt_str), cursor_id
    except ValueError as exc:
        raise ValueError("Invalid pagination cursor") from exc


class TraceService:
    async def list_with_cursor(
        self,
        project_id: str,
        cursor: str | None = None,
        limit: int = 50,
        **filters: str | datetime | None,
    ) -> tuple[list[dict[str, Any]], str | None]:
        cursor_dt, cursor_id = None, None
        if cursor:
            cursor_dt, cursor_id = decode_trace_cursor(cursor)

        conditions = ["project_id = :project_id"]
        params = {"project_id": project_id, "limit": limit + 1}

        if cursor_dt and cursor_id:
            conditions.append("(started_at, id::text) < (:cursor_dt, :cursor_id)")
            params["cursor_dt"] = cursor_dt
            params["cursor_id"] = cursor_id

        if filters.get("model"):
            conditions.append("model = :model")
            params["model"] = filters["model"]

        if filters.get("status"):
            conditions.append("status = :status")
            params["status"] = filters["status"]

        if filters.get("from_dt"):
            conditions.append("started_at >= :from_dt")
            params["from_dt"] = filters["from_dt"]

        if filters.get("to_dt"):
            conditions.append("started_at <= :to_dt")
            params["to_dt"] = filters["to_dt"]

        sql = text(
            f"""
            SELECT id, project_id, started_at, ended_at, total_tokens,
                total_cost_usd, span_count, status
            FROM traces
            WHERE {" AND ".join(conditions)}
            ORDER BY started_at DESC, id DESC
            LIMIT :limit
            """  # nosec B608
        )
        async with get_db(project_id=project_id) as db:
            result = await db.execute(sql, params)
            rows = result.mappings().all()

        has_more = len(rows) > limit
        items = [dict(row) for row in rows[:limit]]
        next_cursor = None
        if has_more and items:
            last = items[-1]
            next_cursor = encode_trace_cursor(last["started_at"], str(last["id"]))

        return items, next_cursor

    async def get_with_spans(
        self,
        trace_id: str,
        project_id: str,
        started_at: datetime | None = None,
    ) -> dict[str, Any] | None:
        async with get_db(project_id=project_id) as db:
            if not started_at:
                r = await db.execute(
                    text(
                        "SELECT started_at FROM traces WHERE id = :tid "
                        "AND project_id = :pid ORDER BY started_at ASC LIMIT 1"
                    ),
                    {"tid": trace_id, "pid": project_id},
                )

                row = r.mappings().one_or_none()
                if not row:
                    return None

                started_at = row["started_at"]

            trace_result = await db.execute(
                text("""
                SELECT id, project_id, started_at, ended_at,
                    total_tokens, total_cost_usd, span_count, status
                FROM traces
                WHERE id = :trace_id AND project_id = :project_id
                    AND started_at = :started_at
            """),
                {
                    "trace_id": trace_id,
                    "project_id": project_id,
                    "started_at": started_at,
                },
            )

            trace_row = trace_result.mappings().one_or_none()
            if not trace_row:
                return None

            spans_result = await db.execute(
                text("""
                SELECT id, trace_id, parent_span_id, name, provider, model,
                    input_tokens, output_tokens, cost_usd, latency_ms,
                    status, error, started_at, payload_s3_key, payload_status,
                    payload_drop_reason, metadata
                FROM spans
                WHERE trace_id = :trace_id AND project_id = :project_id
                AND started_at >= :started_at
                ORDER BY started_at ASC
            """),
                {
                    "trace_id": trace_id,
                    "project_id": project_id,
                    "started_at": started_at,
                },
            )

            spans = [dict(r) for r in spans_result.mappings().all()]

        return {**dict(trace_row), "spans": spans}
