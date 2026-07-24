import json
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager

import structlog
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from starlette.types import ASGIApp, Message, Receive, Scope, Send

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


class PayloadTooLargeError(Exception):
    pass


class PayloadSizeLimitMiddleware:
    def __init__(
        self,
        app: ASGIApp,
        *,
        max_bytes: int = settings.max_request_body_bytes,
    ) -> None:
        self.app = app
        self.max_bytes = max_bytes

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        if scope["type"] != "http":
            await self.app(scope, receive, send)
            return

        content_length = self._content_length(scope)
        if content_length is not None and content_length > self.max_bytes:
            await self._send_too_large(send)
            return

        received_bytes = 0
        response_started = False

        async def limited_receive() -> Message:
            nonlocal received_bytes

            message = await receive()
            if message["type"] == "http.request":
                body = message.get("body", b"")
                received_bytes += len(body)
                if received_bytes > self.max_bytes:
                    raise PayloadTooLargeError

            return message

        async def tracking_send(message: Message) -> None:
            nonlocal response_started

            if message["type"] == "http.response.start":
                response_started = True
            await send(message)

        try:
            await self.app(scope, limited_receive, tracking_send)
        except PayloadTooLargeError:
            if response_started:
                raise
            await self._send_too_large(send)

    @staticmethod
    def _content_length(scope: Scope) -> int | None:
        for name, value in scope.get("headers", []):
            if name == b"content-length":
                try:
                    return int(value)
                except ValueError:
                    return None
        return None

    async def _send_too_large(self, send: Send) -> None:
        body = json.dumps(
            {"error": "payload_too_large", "max_bytes": self.max_bytes},
            separators=(",", ":"),
        ).encode("utf-8")
        headers: list[tuple[bytes, bytes]] = [
            (b"content-type", b"application/json"),
            (b"content-length", str(len(body)).encode("ascii")),
        ]
        await send(
            {
                "type": "http.response.start",
                "status": 413,
                "headers": headers,
            }
        )
        await send({"type": "http.response.body", "body": body})


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
