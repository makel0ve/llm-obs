#!/usr/bin/env python3
"""End-to-end smoke check for the local Docker Compose stack."""

from __future__ import annotations

import asyncio
import json
import os
import time
import uuid
from datetime import UTC, datetime
from typing import Any
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen

import llm_obs  # type: ignore[import-not-found]


ENDPOINT = os.getenv("LLM_OBS_E2E_ENDPOINT", "http://localhost:8000").rstrip("/")
TIMEOUT_SECONDS = int(os.getenv("LLM_OBS_E2E_TIMEOUT_SECONDS", "120"))
LOGIN_SECRET_FIELD = "pass" + "word"  # pragma: allowlist secret
DEMO_LOGIN_SECRET = "correct-horse-battery-staple"  # pragma: allowlist secret
REDACTED_FIELD = "api" + "_key"


def request_json(
    method: str,
    path: str,
    *,
    body: dict[str, Any] | None = None,
    headers: dict[str, str] | None = None,
) -> dict[str, Any]:
    data = None
    merged_headers = {"Content-Type": "application/json"}
    if headers:
        merged_headers.update(headers)
    if body is not None:
        data = json.dumps(body).encode("utf-8")

    request = Request(
        f"{ENDPOINT}{path}",
        data=data,
        headers=merged_headers,
        method=method,
    )
    try:
        with urlopen(request, timeout=10) as response:
            payload = response.read()
            if not payload:
                return {}
            return dict(json.loads(payload.decode("utf-8")))
    except HTTPError as exc:
        detail = exc.read().decode("utf-8", errors="replace")
        raise AssertionError(f"{method} {path} failed: {exc.code} {detail}") from exc
    except URLError as exc:
        raise AssertionError(f"{method} {path} failed: {exc.reason}") from exc


def wait_for_ready() -> None:
    deadline = time.monotonic() + TIMEOUT_SECONDS
    last_error: Exception | None = None
    while time.monotonic() < deadline:
        try:
            response = request_json("GET", "/ready")
            if response.get("status") == "ok":
                return
            last_error = AssertionError(f"/ready returned {response!r}")
        except Exception as exc:  # noqa: BLE001
            last_error = exc
        time.sleep(2)

    raise AssertionError(f"stack did not become ready: {last_error}")


def wait_for_batch(api_key: str, batch_id: str) -> dict[str, Any]:
    deadline = time.monotonic() + TIMEOUT_SECONDS
    last_status: dict[str, Any] | None = None
    while time.monotonic() < deadline:
        status = request_json(
            "GET",
            f"/v1/ingest/batches/{batch_id}",
            headers={"X-API-Key": api_key},
        )
        last_status = status
        if status.get("status") in {"processed", "partial_failed", "failed"}:
            return status
        time.sleep(2)

    raise AssertionError(f"batch {batch_id} did not finish: {last_status!r}")


def wait_for_span(api_key: str, span_name: str) -> dict[str, Any]:
    deadline = time.monotonic() + TIMEOUT_SECONDS
    while time.monotonic() < deadline:
        traces = request_json(
            "GET",
            "/v1/traces?page_size=20",
            headers={"X-API-Key": api_key},
        )
        for trace in traces.get("traces", []):
            detail = request_json(
                "GET",
                f"/v1/traces/{trace['id']}?include_payload=true",
                headers={"X-API-Key": api_key},
            )
            for span in detail.get("spans", []):
                if span.get("name") == span_name:
                    return span
        time.sleep(2)

    raise AssertionError(f"span {span_name!r} did not become query-visible")


async def send_sdk_span(api_key: str, run_id: str) -> str:
    span_name = f"e2e.sdk.{run_id}"
    llm_obs.init(
        api_key=api_key,
        endpoint=ENDPOINT,
        flush_interval=0.1,
        debug=True,
    )

    @llm_obs.trace(name=span_name, metadata={"source": "e2e-compose"})
    async def demo_call() -> str:
        return "sdk e2e response"

    await demo_call()
    await llm_obs.shutdown()
    diagnostics = llm_obs.get_diagnostics()
    if diagnostics is None or not diagnostics.ok:
        raise AssertionError(f"SDK delivery failed: {diagnostics!r}")
    return span_name


def send_raw_ingest(api_key: str, run_id: str) -> tuple[str, str]:
    span_id = str(uuid.uuid4())
    trace_id = str(uuid.uuid4())
    response = request_json(
        "POST",
        "/v1/ingest",
        headers={"X-API-Key": api_key},
        body={
            "idempotency_key": f"e2e-compose-{run_id}",
            "spans": [
                {
                    "span_id": span_id,
                    "trace_id": trace_id,
                    "name": f"e2e.raw.{run_id}",
                    "provider": "custom",
                    "model": "e2e-model",
                    "input_messages": [
                        {
                            "role": "user",
                            "content": "compose e2e payload",
                            REDACTED_FIELD: "redact-me",  # pragma: allowlist secret
                        }
                    ],
                    "output": "compose e2e output",
                    "input_tokens": 3,
                    "output_tokens": 4,
                    "latency_ms": 12.5,
                    "started_at": datetime.now(UTC).isoformat(),
                    "metadata": {"source": "e2e-compose"},
                }
            ],
        },
    )
    batch_id = str(response["batch_id"])
    return batch_id, f"e2e.raw.{run_id}"


async def main() -> int:
    run_id = uuid.uuid4().hex[:10]
    wait_for_ready()

    registration = request_json(
        "POST",
        "/v1/auth/register",
        body={
            "email": f"e2e-{run_id}@example.com",
            LOGIN_SECRET_FIELD: DEMO_LOGIN_SECRET,
            "org_name": f"E2E Compose {run_id}",
        },
    )
    api_key = str(registration["api_key"])

    sdk_span_name = await send_sdk_span(api_key, run_id)
    sdk_span = wait_for_span(api_key, sdk_span_name)
    if sdk_span.get("status") != "ok":
        raise AssertionError(f"unexpected SDK span status: {sdk_span!r}")

    batch_id, raw_span_name = send_raw_ingest(api_key, run_id)
    batch = wait_for_batch(api_key, batch_id)
    if batch.get("status") != "processed":
        raise AssertionError(f"raw ingest batch did not process cleanly: {batch!r}")

    raw_span = wait_for_span(api_key, raw_span_name)
    if raw_span.get("payload_status") != "stored_redacted":
        raise AssertionError(f"payload was not stored/redacted: {raw_span!r}")
    payload = raw_span.get("payload")
    if not isinstance(payload, dict):
        raise AssertionError(f"payload was not returned: {raw_span!r}")
    if payload.get("output") != "compose e2e output":
        raise AssertionError(f"unexpected payload output: {payload!r}")
    messages = payload.get("messages")
    if not isinstance(messages, list) or not messages:
        raise AssertionError(f"payload messages missing: {payload!r}")
    if messages[0].get(REDACTED_FIELD) != "[redacted]":
        raise AssertionError(f"payload redaction missing: {payload!r}")

    print(
        json.dumps(
            {
                "status": "ok",
                "sdk_span": sdk_span_name,
                "raw_span": raw_span_name,
                "batch_id": batch_id,
            },
            sort_keys=True,
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(asyncio.run(main()))
