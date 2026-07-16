import asyncio
from collections.abc import AsyncIterator
from datetime import datetime
from typing import Any

from fastapi import APIRouter, Depends, HTTPException, Query
from fastapi.responses import StreamingResponse

from app.core.auth import get_project_from_token_or_api_key
from app.services.pubsub import pubsub_manager
from app.services.storage import StorageService
from app.services.trace_service import TraceService

router = APIRouter(prefix="/v1", tags=["traces"])


@router.get("/traces")
async def list_traces(
    project: Any = Depends(get_project_from_token_or_api_key),
    from_dt: datetime | None = Query(default=None),
    to_dt: datetime | None = Query(default=None),
    model: str | None = Query(default=None, max_length=100),
    status: str | None = Query(default=None, pattern="^(ok|error)$"),
    cursor: str | None = Query(default=None),
    page_size: int = Query(default=50, ge=1, le=200),
) -> dict[str, Any]:
    service = TraceService()
    try:
        traces, next_cursor = await service.list_with_cursor(
            project_id=str(project["id"]),
            from_dt=from_dt,
            to_dt=to_dt,
            model=model,
            status=status,
            cursor=cursor,
            limit=page_size,
        )
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc

    return {
        "traces": traces,
        "next_cursor": next_cursor,
        "has_more": next_cursor is not None,
    }


@router.get("/traces/{trace_id}")
async def get_trace_detail(
    trace_id: str,
    project: Any = Depends(get_project_from_token_or_api_key),
    include_payload: bool = Query(default=False),
    started_at: datetime | None = Query(default=None),
) -> dict[str, Any]:
    service = TraceService()
    trace = await service.get_with_spans(
        trace_id=trace_id,
        project_id=str(project["id"]),
        started_at=started_at,
    )
    if not trace:
        raise HTTPException(status_code=404, detail="Trace not found")

    if include_payload:
        storage = StorageService()
        s3_keys = [s["payload_s3_key"] for s in trace["spans"] if s["payload_s3_key"]]
        if s3_keys:
            payloads = await asyncio.gather(
                *[storage.get_payload(k) for k in s3_keys], return_exceptions=True
            )
            key_map = {
                k: p
                for k, p in zip(s3_keys, payloads)
                if not isinstance(p, Exception) and p is not None
            }
            for span in trace["spans"]:
                if span["payload_s3_key"] in key_map:
                    span["payload"] = key_map[span["payload_s3_key"]]

    return trace


@router.get("/stream/spans")
async def stream_spans(
    project: Any = Depends(get_project_from_token_or_api_key),
) -> StreamingResponse:
    queue = pubsub_manager.subscribe(str(project["id"]))

    async def generate() -> AsyncIterator[str]:
        try:
            while True:
                try:
                    data = await asyncio.wait_for(queue.get(), timeout=25.0)
                    yield f"data: {data}\n\n"

                except TimeoutError:
                    yield ": keepalive\n\n"

        finally:
            pubsub_manager.unsubscribe(str(project["id"]), queue)

    return StreamingResponse(
        generate(),
        media_type="text/event-stream",
        headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"},
    )
