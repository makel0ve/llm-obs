import asyncio
import random

import httpx
import structlog


log = structlog.get_logger()


class HttpTransport:
    MAX_ATTEMPTS = 3
    BASE_DELAY = 1.0

    def __init__(self, endpoint: str, api_key: str):
        self._client = httpx.AsyncClient(
            base_url=endpoint,
            headers={"X-API-Key": api_key, "User-Agent": "llm-obs-sdk/1.0"},
            timeout=httpx.Timeout(connect=5.0, read=10.0, write=10.0, pool=5.0),
        )

    async def send_batch(self, spans: list[dict]) -> bool:
        for attempt in range(self.MAX_ATTEMPTS):
            try:
                resp = await self._client.post("/v1/ingest", json={"spans": spans})
                resp.raise_for_status()
                log.debug("ingest_batch_sent", spans_count=len(spans), attempt=attempt)
                return True

            except httpx.HTTPStatusError as e:
                if e.response.status_code == 429:
                    retry_after = float(e.response.headers.get("Retry-After", 60))
                    log.warning("ingest_rate_limited", retry_after=retry_after)
                    return False

                elif e.response.status_code >= 500 and attempt < self.MAX_ATTEMPTS - 1:
                    await asyncio.sleep(self._jitter(attempt))

                else:
                    log.error("ingest_http_error", status_code=e.response.status_code)
                    return False

            except (httpx.ConnectError, httpx.TimeoutException) as e:
                if attempt < self.MAX_ATTEMPTS - 1:
                    delay = self._jitter(attempt)
                    log.warning("ingest_connection_error", attempt=attempt, delay=delay)
                    await asyncio.sleep(delay)

                else:
                    log.error("ingest_failed_all_attempts", error=str(e))
                    return False

        return False

    def _jitter(self, attempt: int) -> float:
        base = self.BASE_DELAY * (2**attempt)
        return base + random.uniform(0, base * 0.1)

    async def aclose(self) -> None:
        await self._client.aclose()
