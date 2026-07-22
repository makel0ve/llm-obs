from collections.abc import Iterator

import pytest
from fastapi import FastAPI
from httpx import ASGITransport, AsyncClient

from app.core.security_headers import SECURITY_HEADERS, SecurityHeadersMiddleware
from app.main import app


@pytest.fixture(autouse=True, scope="session")
def patch_app_engine() -> Iterator[None]:
    yield


@pytest.mark.asyncio
async def test_security_headers_middleware_adds_default_headers() -> None:
    test_app = FastAPI()
    test_app.add_middleware(SecurityHeadersMiddleware)

    @test_app.get("/ok")
    async def ok() -> dict[str, bool]:
        return {"ok": True}

    async with AsyncClient(
        transport=ASGITransport(app=test_app),
        base_url="http://test",
    ) as client:
        response = await client.get("/ok")

    for header, value in SECURITY_HEADERS.items():
        assert response.headers[header] == value


def test_main_app_registers_security_headers_middleware() -> None:
    assert any(
        middleware.cls is SecurityHeadersMiddleware
        for middleware in app.user_middleware
    )
