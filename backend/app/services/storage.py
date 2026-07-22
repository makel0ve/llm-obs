import gzip
import json
from collections.abc import Mapping
from dataclasses import dataclass
from typing import Any, Literal, cast

import aioboto3
import structlog
from botocore.exceptions import ClientError

from app.core.config import settings
from app.core.metrics import payload_storage_failures

log = structlog.get_logger()
DEFAULT_PAYLOAD_MAX_BYTES = 256 * 1024
DEFAULT_REDACT_KEYS = "api_key,password,secret,token,authorization"
REDACTED_VALUE = "[redacted]"
MISSING_BUCKET_CODES = frozenset({"404", "NoSuchBucket", "NotFound"})

PayloadStorageStatus = Literal[
    "stored",
    "stored_redacted",
    "omitted",
    "too_large",
    "storage_failed",
]


@dataclass(frozen=True)
class PayloadStorageResult:
    s3_key: str | None
    status: PayloadStorageStatus
    drop_reason: str | None = None


def is_missing_bucket_error(exc: Exception) -> bool:
    if not isinstance(exc, ClientError):
        return False

    response = exc.response
    error_code = str(response.get("Error", {}).get("Code", ""))
    http_status = response.get("ResponseMetadata", {}).get("HTTPStatusCode")
    return error_code in MISSING_BUCKET_CODES or http_status == 404


async def check_payload_bucket() -> str:
    session = aioboto3.Session()
    async with session.client(
        "s3",
        endpoint_url=settings.s3_endpoint_url,
        aws_access_key_id=settings.aws_access_key_id.get_secret_value(),
        aws_secret_access_key=settings.aws_secret_access_key.get_secret_value(),
    ) as s3:
        try:
            await s3.head_bucket(Bucket=settings.s3_bucket)
            return "ok"

        except Exception as exc:
            if is_missing_bucket_error(exc):
                return "missing"

            payload_storage_failures.labels(stage="readiness").inc()
            log.warning("s3_readiness_degraded", error=str(exc))
            return "degraded"


async def ensure_payload_bucket() -> str:
    session = aioboto3.Session()
    async with session.client(
        "s3",
        endpoint_url=settings.s3_endpoint_url,
        aws_access_key_id=settings.aws_access_key_id.get_secret_value(),
        aws_secret_access_key=settings.aws_secret_access_key.get_secret_value(),
    ) as s3:
        try:
            await s3.head_bucket(Bucket=settings.s3_bucket)
            return "ok"

        except Exception as exc:
            if not is_missing_bucket_error(exc):
                payload_storage_failures.labels(stage="startup").inc()
                log.warning("s3_startup_degraded", error=str(exc))
                return "degraded"

        try:
            await s3.create_bucket(Bucket=settings.s3_bucket)
            log.info("s3_bucket_created", bucket=settings.s3_bucket)
            return "created"

        except Exception as exc:
            payload_storage_failures.labels(stage="startup").inc()
            log.warning("s3_bucket_create_failed", error=str(exc))
            return "degraded"


def parse_redact_keys(value: str | None) -> set[str]:
    if not value:
        value = DEFAULT_REDACT_KEYS

    return {item.strip().lower() for item in value.split(",") if item.strip()}


def redact_payload(value: Any, redact_keys: set[str]) -> Any:
    if isinstance(value, list):
        return [redact_payload(item, redact_keys) for item in value]

    if isinstance(value, Mapping):
        redacted: dict[str, Any] = {}
        for key, item in value.items():
            key_text = str(key)
            if key_text.lower() in redact_keys:
                redacted[key_text] = REDACTED_VALUE
            else:
                redacted[key_text] = redact_payload(item, redact_keys)
        return redacted

    return value


def should_store_payload(mode: str, has_error: bool) -> bool:
    if mode == "none":
        return False
    if mode == "errors":
        return has_error
    return True


class StorageService:
    def __init__(self) -> None:
        self._session = aioboto3.Session()

    async def store_payload(
        self,
        project_id: str,
        span_id: str,
        messages: list[dict[str, Any]],
        output: str | None,
        max_bytes: int | None = DEFAULT_PAYLOAD_MAX_BYTES,
        redact_keys: set[str] | None = None,
    ) -> PayloadStorageResult:
        payload_data = {"messages": messages, "output": output}
        if redact_keys:
            payload_data = redact_payload(payload_data, redact_keys)

        payload = json.dumps(payload_data, ensure_ascii=False)
        payload_bytes = payload.encode("utf-8")
        if max_bytes is not None and len(payload_bytes) > max_bytes:
            log.info(
                "payload_dropped_by_size",
                project_id=project_id,
                span_id=span_id,
                payload_bytes=len(payload_bytes),
                max_bytes=max_bytes,
            )
            return PayloadStorageResult(
                s3_key=None, status="too_large", drop_reason="max_bytes_exceeded"
            )

        compressed = gzip.compress(payload_bytes, compresslevel=6)
        key = f"payloads/{project_id}/{span_id[:2]}/{span_id}.json.gz"

        try:
            async with self._session.client(
                "s3",
                endpoint_url=settings.s3_endpoint_url,
                aws_access_key_id=settings.aws_access_key_id.get_secret_value(),
                aws_secret_access_key=settings.aws_secret_access_key.get_secret_value(),
            ) as s3:
                await s3.put_object(
                    Bucket=settings.s3_bucket,
                    Key=key,
                    Body=compressed,
                    ContentEncoding="gzip",
                    ContentType="application/json",
                )

            return PayloadStorageResult(
                s3_key=key,
                status="stored_redacted" if redact_keys else "stored",
                drop_reason=None,
            )

        except Exception as e:
            payload_storage_failures.labels(stage="store").inc()
            log.error("s3_store_failed", span_id=span_id, error=str(e))
            return PayloadStorageResult(
                s3_key=None, status="storage_failed", drop_reason="s3_error"
            )

    async def get_payload(self, s3_key: str) -> dict[str, Any] | None:
        try:
            async with self._session.client(
                "s3",
                endpoint_url=settings.s3_endpoint_url,
                aws_access_key_id=settings.aws_access_key_id.get_secret_value(),
                aws_secret_access_key=settings.aws_secret_access_key.get_secret_value(),
            ) as s3:
                response = await s3.get_object(Bucket=settings.s3_bucket, Key=s3_key)
                data = gzip.decompress(await response["Body"].read())
                return cast(dict[str, Any], json.loads(data))

        except Exception as e:
            log.error("s3_get_failed", key=s3_key, error=str(e))
            return None
