from collections.abc import Iterator
from typing import Any

import pytest
from botocore.exceptions import ClientError

from app.services import storage


@pytest.fixture(autouse=True, scope="session")
def patch_app_engine() -> Iterator[None]:
    yield


def client_error(code: str, status: int) -> ClientError:
    return ClientError(
        {
            "Error": {"Code": code, "Message": "simulated"},
            "ResponseMetadata": {
                "HTTPStatusCode": status,
                "HTTPHeaders": {},
                "HostId": "host",
                "RequestId": "request",
                "RetryAttempts": 0,
            },
        },
        "HeadBucket",
    )


class FakeS3Client:
    def __init__(self, *, head_error: Exception | None = None) -> None:
        self.head_error = head_error
        self.created_buckets: list[str] = []

    async def __aenter__(self) -> "FakeS3Client":
        return self

    async def __aexit__(self, exc_type: object, exc: object, tb: object) -> None:
        return None

    async def head_bucket(self, **kwargs: Any) -> None:
        if self.head_error:
            raise self.head_error

    async def create_bucket(self, **kwargs: Any) -> None:
        self.created_buckets.append(str(kwargs["Bucket"]))


class FakeSession:
    def __init__(self, client: FakeS3Client) -> None:
        self.client_instance = client

    def client(self, *args: Any, **kwargs: Any) -> FakeS3Client:
        return self.client_instance


@pytest.mark.asyncio
async def test_ensure_payload_bucket_creates_only_when_bucket_is_missing(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    fake_client = FakeS3Client(head_error=client_error("NoSuchBucket", 404))
    monkeypatch.setattr(storage.aioboto3, "Session", lambda: FakeSession(fake_client))

    status = await storage.ensure_payload_bucket()

    assert status == "created"
    assert fake_client.created_buckets == [storage.settings.s3_bucket]


@pytest.mark.asyncio
async def test_ensure_payload_bucket_does_not_create_on_infrastructure_error(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    fake_client = FakeS3Client(head_error=client_error("AccessDenied", 403))
    monkeypatch.setattr(storage.aioboto3, "Session", lambda: FakeSession(fake_client))

    status = await storage.ensure_payload_bucket()

    assert status == "degraded"
    assert fake_client.created_buckets == []


@pytest.mark.asyncio
async def test_check_payload_bucket_reports_degraded_without_leaking_exception(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    fake_client = FakeS3Client(head_error=RuntimeError("secret endpoint timeout"))
    monkeypatch.setattr(storage.aioboto3, "Session", lambda: FakeSession(fake_client))

    status = await storage.check_payload_bucket()

    assert status == "degraded"
    assert fake_client.created_buckets == []
