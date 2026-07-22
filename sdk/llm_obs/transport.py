import asyncio
import random
from dataclasses import dataclass

import httpx
import structlog

from llm_obs.version import user_agent


log = structlog.get_logger()


@dataclass(frozen=True)
class TransportDiagnostics:
    ok: bool
    reason: str
    spans_count: int
    attempts: int
    status_code: int | None = None
    retry_after: float | None = None
    error_type: str | None = None


class HttpTransport:
    MAX_ATTEMPTS = 3
    BASE_DELAY = 1.0

    def __init__(self, endpoint: str, api_key: str, *, debug: bool = False):
        self._debug = debug
        self.last_diagnostics: TransportDiagnostics | None = None
        self._client = httpx.AsyncClient(
            base_url=endpoint,
            headers={"X-API-Key": api_key, "User-Agent": user_agent()},
            timeout=httpx.Timeout(connect=5.0, read=10.0, write=10.0, pool=5.0),
            trust_env=False,
        )

    async def send_batch(
        self, spans: list[dict], *, idempotency_key: str | None = None
    ) -> bool:
        spans_count = len(spans)
        payload = {"spans": spans, "idempotency_key": idempotency_key}
        for attempt in range(self.MAX_ATTEMPTS):
            try:
                resp = await self._client.post("/v1/ingest", json=payload)
                resp.raise_for_status()
                self._record_diagnostics(
                    TransportDiagnostics(
                        ok=True,
                        reason="sent",
                        spans_count=spans_count,
                        attempts=attempt + 1,
                        status_code=resp.status_code,
                    )
                )
                return True

            except httpx.HTTPStatusError as e:
                if e.response.status_code == 429:
                    retry_after = float(e.response.headers.get("Retry-After", 60))
                    self._record_diagnostics(
                        TransportDiagnostics(
                            ok=False,
                            reason="rate_limited",
                            spans_count=spans_count,
                            attempts=attempt + 1,
                            status_code=e.response.status_code,
                            retry_after=retry_after,
                        )
                    )
                    return False

                elif e.response.status_code >= 500 and attempt < self.MAX_ATTEMPTS - 1:
                    if self._debug:
                        log.debug(
                            "llm_obs_ingest_retry",
                            reason="server_error",
                            status_code=e.response.status_code,
                            attempt=attempt + 1,
                            spans_count=spans_count,
                        )
                    await asyncio.sleep(self._jitter(attempt))

                else:
                    self._record_diagnostics(
                        TransportDiagnostics(
                            ok=False,
                            reason="http_error",
                            spans_count=spans_count,
                            attempts=attempt + 1,
                            status_code=e.response.status_code,
                        )
                    )
                    return False

            except (httpx.ConnectError, httpx.TimeoutException) as e:
                if attempt < self.MAX_ATTEMPTS - 1:
                    delay = self._jitter(attempt)
                    if self._debug:
                        log.debug(
                            "llm_obs_ingest_retry",
                            reason="connection_error",
                            error_type=type(e).__name__,
                            attempt=attempt + 1,
                            delay=delay,
                            spans_count=spans_count,
                        )
                    await asyncio.sleep(delay)

                else:
                    self._record_diagnostics(
                        TransportDiagnostics(
                            ok=False,
                            reason="connection_error",
                            spans_count=spans_count,
                            attempts=attempt + 1,
                            error_type=type(e).__name__,
                        )
                    )
                    return False

        self._record_diagnostics(
            TransportDiagnostics(
                ok=False,
                reason="unknown_failure",
                spans_count=spans_count,
                attempts=self.MAX_ATTEMPTS,
            )
        )
        return False

    def _record_diagnostics(self, diagnostics: TransportDiagnostics) -> None:
        self.last_diagnostics = diagnostics
        if diagnostics.ok:
            if self._debug:
                log.debug("llm_obs_ingest_sent", **diagnostics.__dict__)
            return

        log.warning("llm_obs_ingest_failed", **diagnostics.__dict__)

    def _jitter(self, attempt: int) -> float:
        base = self.BASE_DELAY * (2**attempt)
        return base + random.uniform(0, base * 0.1)

    async def aclose(self) -> None:
        await self._client.aclose()
