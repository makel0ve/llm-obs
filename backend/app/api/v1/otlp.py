import importlib
from typing import Any, Protocol, cast

from fastapi import APIRouter, Depends, Request, Response, status
from pydantic import ValidationError
from redis.asyncio import Redis

from app.core.auth import get_project_from_api_key
from app.core.ratelimit import RateLimiter, get_rate_limiter
from app.core.redis import get_redis
from app.schemas.ingest import SpanSchema
from app.services.otlp import OTLPConverter

router = APIRouter(tags=["otlp"])


class BatchAcceptor(Protocol):
    async def accept_batch(self, project_id: str, spans: list[SpanSchema]) -> object:
        """Accept validated spans for async processing."""


def get_otlp_ingest_service(redis: Redis = Depends(get_redis)) -> BatchAcceptor:
    ingest_module = importlib.import_module("app.services.ingest")
    ingest_service = cast(Any, getattr(ingest_module, "IngestService"))

    return cast(BatchAcceptor, ingest_service(redis=redis))


@router.post("/v1/traces")
async def receive_otlp(
    request: Request,
    response: Response,
    project: Any = Depends(get_project_from_api_key),
    service: BatchAcceptor = Depends(get_otlp_ingest_service),
    rate_limiter: RateLimiter = Depends(get_rate_limiter),
) -> dict[str, Any]:
    await rate_limiter.check(project_id=str(project["id"]), response=response)

    body = await request.body()
    content_type = request.headers.get("content-type", "")
    spans = OTLPConverter().parse(body, content_type)
    if spans is None:
        response.status_code = status.HTTP_400_BAD_REQUEST
        return {
            "error": "Unable to parse OTLP trace export",
        }

    accepted_spans = []
    rejected_count = 0
    validation_errors: list[str] = []
    if spans:
        for span in spans:
            try:
                accepted_spans.append(SpanSchema(**span))
            except ValidationError as exc:
                rejected_count += 1
                validation_errors.append(str(exc.errors()[0].get("msg", exc)))

        if accepted_spans:
            await service.accept_batch(str(project["id"]), accepted_spans)

    if rejected_count:
        return {
            "partialSuccess": {
                "rejectedSpans": rejected_count,
                "errorMessage": "; ".join(validation_errors[:3]),
            }
        }

    return {}
