from collections.abc import Callable
from contextlib import asynccontextmanager

import aioboto3
import structlog
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from starlette.middleware.base import BaseHTTPMiddleware
from starlette.requests import Request
from starlette.responses import Response

from app.api.v1 import alerts, auth, health, ingest, metrics, otlp, projects, traces
from app.core.config import settings
from app.core.metrics import setup_metrics

log = structlog.get_logger()


@asynccontextmanager
async def lifespan(app: FastAPI):
    session = aioboto3.Session()
    async with session.client(
        "s3",
        endpoint_url=settings.s3_endpoint_url,
        aws_access_key_id=settings.aws_access_key_id.get_secret_value(),
        aws_secret_access_key=settings.aws_secret_access_key.get_secret_value(),
    ) as s3:
        try:
            await s3.head_bucket(Bucket=settings.s3_bucket)

        except Exception:
            await s3.create_bucket(Bucket=settings.s3_bucket)
            log.info("s3_bucket_created", bucket=settings.s3_bucket)

    yield


app = FastAPI(
    title="LLM Obs API",
    version="1.0.0",
    docs_url="/docs" if settings.environment != "production" else None,
    redoc_url="/redoc" if settings.environment != "production" else None,
    lifespan=lifespan,
)

setup_metrics(app)

app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.cors_allowed_origins,
    allow_credentials=True,
    allow_methods=["GET", "POST", "PUT", "PATCH", "DELETE"],
    allow_headers=["Authorization", "X-API-Key", "Content-Type", "Idempotency-Key"],
)


class PayloadSizeLimitMiddleware(BaseHTTPMiddleware):
    MAX_BYTES = 10 * 1024 * 1024

    async def dispatch(self, request: Request, call_next: Callable) -> Response:
        cl = request.headers.get("content-length")

        if cl and int(cl) > self.MAX_BYTES:
            return Response(
                content='{"error": "payload_too_large", "max_bytes": 10485760}',
                status_code=413,
                media_type="application/json",
            )

        return await call_next(request)


app.add_middleware(PayloadSizeLimitMiddleware)

for router in [
    ingest.router,
    traces.router,
    metrics.router,
    alerts.router,
    auth.router,
    projects.router,
    health.router,
    otlp.router,
]:
    app.include_router(router=router)
