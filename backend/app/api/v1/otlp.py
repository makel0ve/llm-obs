from fastapi import APIRouter, Depends, Request, Response

from app.core.auth import get_project_from_api_key
from app.core.ratelimit import RateLimiter, get_rate_limiter
from app.schemas.ingest import SpanSchema
from app.services.ingest import IngestService, get_ingest_service
from app.services.otlp import OTLPConverter

router = APIRouter(tags=["otlp"])


@router.post("/v1/traces")
async def receive_otlp(
    request: Request,
    response: Response,
    project=Depends(get_project_from_api_key),
    service: IngestService = Depends(get_ingest_service),
    rate_limiter: RateLimiter = Depends(get_rate_limiter),
):
    await rate_limiter.check(project_id=str(project["id"]), response=response)

    body = await request.body()
    content_type = request.headers.get("content-type", "")
    spans = OTLPConverter().parse(body, content_type)

    if spans:
        span_schemas = [SpanSchema(**s) for s in spans]
        await service.accept_batch(str(project["id"]), span_schemas)

    return {"partialSuccess": {}}
