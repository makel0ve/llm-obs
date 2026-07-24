import json
from collections.abc import Iterator
from typing import Any

import pytest
from starlette.types import Message, Receive, Scope, Send

from app.main import PayloadSizeLimitMiddleware


@pytest.fixture(autouse=True, scope="session")
def patch_app_engine() -> Iterator[None]:
    yield


async def _body_reading_app(scope: Scope, receive: Receive, send: Send) -> None:
    while True:
        message = await receive()
        if message["type"] != "http.request" or not message.get("more_body", False):
            break

    body = b'{"ok":true}'
    await send(
        {
            "type": "http.response.start",
            "status": 200,
            "headers": [
                (b"content-type", b"application/json"),
                (b"content-length", str(len(body)).encode("ascii")),
            ],
        }
    )
    await send({"type": "http.response.body", "body": body})


async def _run_request(
    *,
    middleware: PayloadSizeLimitMiddleware,
    headers: list[tuple[bytes, bytes]],
    messages: list[Message],
) -> list[Message]:
    sent: list[Message] = []

    async def receive() -> Message:
        if messages:
            return messages.pop(0)
        return {"type": "http.disconnect"}

    async def send(message: Message) -> None:
        sent.append(message)

    await middleware(
        {
            "type": "http",
            "method": "POST",
            "path": "/v1/ingest",
            "headers": headers,
        },
        receive,
        send,
    )
    return sent


def _status(sent: list[Message]) -> int:
    start = next(
        message for message in sent if message["type"] == "http.response.start"
    )
    return int(start["status"])


def _json_body(sent: list[Message]) -> dict[str, Any]:
    body = b"".join(
        message.get("body", b"")
        for message in sent
        if message["type"] == "http.response.body"
    )
    return dict(json.loads(body))


@pytest.mark.asyncio
async def test_payload_size_limit_rejects_content_length_without_reading_body() -> None:
    async def app_that_must_not_run(
        scope: Scope,
        receive: Receive,
        send: Send,
    ) -> None:
        raise AssertionError("downstream app should not run")

    middleware = PayloadSizeLimitMiddleware(app_that_must_not_run, max_bytes=10)

    sent = await _run_request(
        middleware=middleware,
        headers=[(b"content-length", b"11")],
        messages=[{"type": "http.request", "body": b"not-read", "more_body": False}],
    )

    assert _status(sent) == 413
    assert _json_body(sent) == {"error": "payload_too_large", "max_bytes": 10}


@pytest.mark.asyncio
async def test_payload_size_limit_allows_body_at_limit() -> None:
    middleware = PayloadSizeLimitMiddleware(_body_reading_app, max_bytes=10)

    sent = await _run_request(
        middleware=middleware,
        headers=[],
        messages=[{"type": "http.request", "body": b"1234567890", "more_body": False}],
    )

    assert _status(sent) == 200


@pytest.mark.asyncio
async def test_payload_size_limit_rejects_chunked_body_without_content_length() -> None:
    middleware = PayloadSizeLimitMiddleware(_body_reading_app, max_bytes=10)

    sent = await _run_request(
        middleware=middleware,
        headers=[],
        messages=[
            {"type": "http.request", "body": b"12345", "more_body": True},
            {"type": "http.request", "body": b"678901", "more_body": False},
        ],
    )

    assert _status(sent) == 413
    assert _json_body(sent) == {"error": "payload_too_large", "max_bytes": 10}


@pytest.mark.asyncio
async def test_payload_size_limit_streams_multiple_chunks_within_limit() -> None:
    middleware = PayloadSizeLimitMiddleware(_body_reading_app, max_bytes=10)

    sent = await _run_request(
        middleware=middleware,
        headers=[],
        messages=[
            {"type": "http.request", "body": b"1234", "more_body": True},
            {"type": "http.request", "body": b"5678", "more_body": False},
        ],
    )

    assert _status(sent) == 200
