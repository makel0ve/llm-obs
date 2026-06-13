import os
import random
import uuid
from datetime import UTC, datetime

from locust import HttpUser, between, task


class SDKUser(HttpUser):
    wait_time = between(0.05, 0.2)

    def on_start(self):
        self.headers = {"X-API-Key": os.getenv("API_KEY", "llmobs_your_api_key_here")}

    @task(10)
    def ingest_batch(self):
        spans = [self._span() for _ in range(random.randint(5, 10))]
        with self.client.post(
            "/v1/ingest",
            json={"spans": spans, "idempotency_key": str(uuid.uuid4())},
            headers=self.headers,
            catch_response=True,
        ) as r:
            if r.status_code == 202:
                r.success()

            elif r.status_code == 429:
                r.failure("Rate limited")

            else:
                r.failure(f"HTTP {r.status_code}")

    @task(2)
    def get_overview(self):
        self.client.get("/v1/metrics/overview?period=24h", headers=self.headers)

    @task(1)
    def list_traces(self):
        self.client.get("/v1/traces?page_size=50", headers=self.headers)

    def _span(self):
        m = random.choice(["gpt-4o", "gpt-4o-mini", "claude-sonnet-4-5"])

        return {
            "span_id": str(uuid.uuid4()),
            "trace_id": str(uuid.uuid4()),
            "provider": "openai" if "gpt" in m else "anthropic",
            "model": m,
            "input_tokens": random.randint(100, 3000),
            "output_tokens": random.randint(50, 800),
            "latency_ms": abs(random.gauss(700, 200)),
            "started_at": datetime.now(UTC).isoformat(),
            "input_messages": [{"role": "user", "content": "load test"}],
        }
