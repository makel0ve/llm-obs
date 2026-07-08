from fastapi import APIRouter, Depends, HTTPException, Response, status

from app.core.auth import get_project_from_api_key
from app.core.ratelimit import RateLimiter, get_rate_limiter
from app.schemas.ingest import BatchStatusResponse, IngestRequest, IngestResponse
from app.services.ingest import IngestService, get_ingest_service

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

    if payload.idempotency_key:
        existing = await service.get_idempotency_result(
            project_id=str(project["id"]), key=payload.idempotency_key
        )

        if existing:
            return IngestResponse(**existing)

    batch_id = await service.accept_batch(
        project_id=str(project["id"]), spans=payload.spans
    )

    result = IngestResponse(batch_id=batch_id, accepted=len(payload.spans))

    if payload.idempotency_key:
        await service.save_idempotency_result(
            project_id=str(project["id"]),
            key=payload.idempotency_key,
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
