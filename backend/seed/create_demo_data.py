import asyncio
import hashlib
import random
import uuid
from datetime import UTC, datetime, timedelta

from sqlalchemy import text

from app.core.db import get_db

MODELS = [
    ("openai", "gpt-4o"),
    ("openai", "gpt-4o-mini"),
    ("anthropic", "claude-sonnet-4-5"),
]


async def seed():
    async with get_db() as db:
        org_id = str(uuid.uuid4())
        await db.execute(
            text(
                "INSERT INTO organizations (id, name, slug) VALUES (:id, :name, :slug) "
                "ON CONFLICT DO NOTHING"
            ),
            {"id": org_id, "name": "Demo Org", "slug": "demo-org"},
        )

        raw_key = "llmobs_demo_key_for_development_only"
        key_hash = hashlib.sha256(raw_key.encode()).hexdigest()
        project_id = str(uuid.uuid4())
        await db.execute(
            text(
                """
            INSERT INTO projects (id, org_id, name, api_key_hash, retention_days)
            VALUES (:id, :org, 'Default', :hash, :retention)
            ON CONFLICT DO NOTHING
            """
            ),
            {"id": project_id, "org": org_id, "hash": key_hash, "retention": 90},
        )

        now = datetime.now(UTC)
        spans = []
        for i in range(2000):
            provider, model = random.choice(MODELS)
            hours_ago = random.expovariate(1 / 24)
            started_at = now - timedelta(hours=(min(hours_ago, 7 * 24)))
            spans.append(
                {
                    "id": str(uuid.uuid4()),
                    "trace_id": str(uuid.uuid4()),
                    "project_id": project_id,
                    "name": random.choice(
                        ["llm.completion", "rag.retrieve", "agent.step"]
                    ),
                    "provider": provider,
                    "model": model,
                    "input_tokens": max(0, int(random.gauss(800, 300))),
                    "output_tokens": max(0, int(random.gauss(250, 100))),
                    "latency_ms": max(50, random.gauss(750, 200)),
                    "cost_usd": round(random.uniform(0.001, 0.05), 8),
                    "status": "error" if random.random() < 0.04 else "ok",
                    "started_at": started_at,
                    "metadata": "{}",
                }
            )

        await db.execute(
            text(
                """
            INSERT INTO spans (id, trace_id, project_id, name, provider, model,
                input_tokens, output_tokens, cost_usd, latency_ms,
                status, started_at, metadata)
            VALUES (:id, :trace_id, :project_id, :name, :provider, :model,
                :input_tokens, :output_tokens, :cost_usd, :latency_ms,
                :status, :started_at, :metadata)
            """
            ),
            spans,
        )

        await db.commit()

        print(f"✓ Demo data: 2000 spans, API key: {raw_key}")


asyncio.run(seed())
