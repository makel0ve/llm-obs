import gzip
import json
from collections.abc import Mapping
from dataclasses import dataclass
from typing import Any, Literal, cast

import aioboto3
import structlog

from app.core.config import settings

log = structlog.get_logger()
S3_THRESHOLD_BYTES = 4 * 1024
DEFAULT_PAYLOAD_MAX_BYTES = 256 * 1024
DEFAULT_REDACT_KEYS = "api_key,password,secret,token,authorization"
REDACTED_VALUE = "[redacted]"

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

        if len(payload_bytes) < S3_THRESHOLD_BYTES:
            return PayloadStorageResult(
                s3_key=None, status="omitted", drop_reason="below_inline_threshold"
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
