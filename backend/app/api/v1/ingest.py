from fastapi import APIRouter, Depends, HTTPException, Response, status

from app.core.auth import get_project_from_api_key
from app.core.ratelimit import RateLimiter, get_rate_limiter
from app.schemas.ingest import BatchStatusResponse, IngestRequest, IngestResponse
from app.services.ingest import (
    IdempotencyConflictError,
    IdempotencyInProgressError,
    IngestService,
    get_ingest_service,
    ingest_request_hash,
)

router = APIRouter(prefix="/v1", tags=["ingest"])


@router.post(
    "/ingest", response_model=IngestResponse, status_code=status.HTTP_202_ACCEPTED
)
async def ingest_spans(
    payload: IngestRequest,
    response: Response,
    project=Depends(get_project_from_api_key),
    service: IngestService = Depends(get_ingest_service),
    rate_limiter: RateLimiter = Depends(get_rate_limiter),
):
    await rate_limiter.check(project_id=str(project["id"]), response=response)

    project_id = str(project["id"])
    batch_id = None
    request_hash = None
    idempotency_result = None

    if payload.idempotency_key:
        batch_id = await service.new_batch_id()
        idempotency_result = IngestResponse(
            batch_id=batch_id, accepted=len(payload.spans)
        )
        request_hash = ingest_request_hash(payload.spans)
        try:
            existing = await service.reserve_idempotency_result(
                project_id=project_id,
                key=payload.idempotency_key,
                request_hash=request_hash,
                result=idempotency_result.model_dump(),
            )
        except IdempotencyConflictError:
            raise HTTPException(
                status_code=409,
                detail="Idempotency key was already used with a different request body",
            )
        except IdempotencyInProgressError:
            raise HTTPException(
                status_code=409,
                detail="Idempotency key is already being processed",
            )

        if existing:
            return IngestResponse(**existing)

    try:
        accepted_batch_id = await service.accept_batch(
            project_id=project_id, spans=payload.spans, batch_id=batch_id
        )
    except Exception:
        if payload.idempotency_key and request_hash:
            await service.mark_idempotency_failed(
                project_id=project_id,
                key=payload.idempotency_key,
                request_hash=request_hash,
            )
        raise

    result = IngestResponse(batch_id=accepted_batch_id, accepted=len(payload.spans))
    if payload.idempotency_key and request_hash and idempotency_result:
        await service.commit_idempotency_result(
            project_id=project_id,
            key=payload.idempotency_key,
            request_hash=request_hash,
            result=result.model_dump(),
        )

    return result


@router.get("/ingest/batches/{batch_id}", response_model=BatchStatusResponse)
async def get_ingest_batch_status(
    batch_id: str,
    project=Depends(get_project_from_api_key),
    service: IngestService = Depends(get_ingest_service),
):
    batch_status = await service.get_batch_status(
        project_id=str(project["id"]), batch_id=batch_id
    )

    if not batch_status:
        raise HTTPException(status_code=404, detail="Batch not found")

    return batch_status
