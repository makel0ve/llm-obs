from collections.abc import AsyncIterator, Awaitable, Callable
from contextlib import asynccontextmanager

import structlog
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from starlette.middleware.base import BaseHTTPMiddleware
from starlette.requests import Request
from starlette.responses import Response

from app.api.v1 import (
    alerts,
    audit,
    auth,
    failed_tasks,
    health,
    ingest,
    metrics,
    otlp,
    pricing,
    projects,
    traces,
    users,
)
from app.core.config import settings
from app.core.metrics import setup_metrics
from app.core.redis import get_redis
from app.core.security_headers import SecurityHeadersMiddleware
from app.services.pubsub import pubsub_manager
from app.services.storage import ensure_payload_bucket

log = structlog.get_logger()


@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncIterator[None]:
    app.state.payload_bucket_status = await ensure_payload_bucket()

    redis = await get_redis()
    await pubsub_manager.start(redis)

    try:
        yield

    finally:
        await pubsub_manager.stop()


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


class PayloadSizeLimitMiddleware(BaseHTTPMiddleware):  # type: ignore[misc]
    MAX_BYTES = 10 * 1024 * 1024

    async def dispatch(
        self,
        request: Request,
        call_next: Callable[[Request], Awaitable[Response]],
    ) -> Response:
        cl = request.headers.get("content-length")

        if cl and int(cl) > self.MAX_BYTES:
            return Response(
                content='{"error": "payload_too_large", "max_bytes": 10485760}',
                status_code=413,
                media_type="application/json",
            )

        return await call_next(request)


app.add_middleware(PayloadSizeLimitMiddleware)
app.add_middleware(SecurityHeadersMiddleware)

for router in [
    ingest.router,
    traces.router,
    metrics.router,
    alerts.router,
    audit.router,
    failed_tasks.router,
    pricing.router,
    auth.router,
    projects.router,
    users.router,
    health.router,
    otlp.router,
]:
    app.include_router(router=router)
