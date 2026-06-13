import gzip
import json

import aioboto3
import structlog

from app.core.config import settings

log = structlog.get_logger()
S3_THRESHOLD_BYTES = 4 * 1024


class StorageService:
    def __init__(self):
        self._session = aioboto3.Session()

    async def store_payload(
        self, project_id: str, span_id: str, messages: list[dict], output: str | None
    ) -> str | None:
        payload = json.dumps(
            {"messages": messages, "output": output}, ensure_ascii=False
        )
        payload_bytes = payload.encode("utf-8")
        if len(payload_bytes) < S3_THRESHOLD_BYTES:
            return None

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

            return key

        except Exception as e:
            log.error("s3_store_failed", span_id=span_id, error=str(e))
            return None

    async def get_payload(self, s3_key: str) -> dict | None:
        try:
            async with self._session.client(
                "s3",
                endpoint_url=settings.s3_endpoint_url,
                aws_access_key_id=settings.aws_access_key_id.get_secret_value(),
                aws_secret_access_key=settings.aws_secret_access_key.get_secret_value(),
            ) as s3:
                response = await s3.get_object(Bucket=settings.s3_bucket, Key=s3_key)
                data = gzip.decompress(await response["Body"].read())
                return json.loads(data)

        except Exception as e:
            log.error("s3_get_failed", key=s3_key, error=str(e))
            return None
