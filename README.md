# LLM Obs — Self-hosted LLM Observability

Track costs, latency, errors and anomalies for every LLM call.
Open-source, privacy-first alternative to LangSmith and Helicone.

![Dashboard](docs/assets/dashboard.png)

---

## What is LLM Obs?

LLM Obs is a self-hosted platform for monitoring LLM calls. Your data never leaves your infrastructure. Deploy it once, connect your Python projects in minutes.

---

## Features

- **Python SDK** — `@trace` decorator and async OpenAI/Anthropic patching
- **Overview dashboard** — spans, P95 latency, error rate, cost and trend charts
- **Trace explorer** — filter recent traces, inspect spans and load stored payloads on demand
- **Cost tracking** — per model and provider with editable historical pricing records
- **Alerts** — latency, error-rate and cost rules with email or Slack targets
- **User management** — admin-created invites, role changes and guarded deletion
- **Audit log** — governance events for settings, users and API key changes
- **Payload privacy** — control large payload storage, max object size and redaction keys
- **Managed API keys** — scoped ingest/read/read-write keys with one-time reveal and revoke
- **OpenTelemetry** — OTLP HTTP endpoint for existing instrumentation
- **Multi-tenant foundation** — organizations, projects, users and project API keys
- **Data retention** — automatic cleanup with per-project policies
- **Self-hosted** — Docker Compose, with experimental Helm manifests

---

## Quick Start

This path starts a local stack and sends one safe demo trace. It does not call
an external LLM provider.

```bash
git clone https://github.com/makel0ve/llm-obs
cd llm-obs

# Copy local development environment variables
cp backend/.env.example backend/.env

# Start the local stack
docker compose -f infra/docker-compose.yml up -d

# Apply migrations
docker compose -f infra/docker-compose.yml exec backend alembic upgrade head

# Open dashboard and create the first account
open http://localhost:3000
```

The first account creates an organization, default project and default project
API key. Save the key when it is shown. API keys are displayed once.

Send the first trace from the host:

```bash
cd sdk
pip install -e .
cd ..

export LLM_OBS_API_KEY=llmobs_your_key_here
export LLM_OBS_ENDPOINT=http://localhost:8000
python examples/sdk_smoke_demo.py
```

Open `http://localhost:3000`, use the `1h` or `24h` range, and check Overview
or Traces. The demo trace name is `examples.sdk_smoke_demo`.

For a production-style Docker Compose start, copy `backend/.env.example` to
`backend/.env.prod`, copy `infra/.env.example` to `infra/.env`, set a strong
`SECRET_KEY`, keep PostgreSQL/MinIO credentials consistent, and run:

```bash
docker compose --env-file infra/.env -f infra/docker-compose.prod.yml up -d
docker compose --env-file infra/.env -f infra/docker-compose.prod.yml exec backend alembic upgrade head
```

Register the first admin through the dashboard or API:

```bash
curl -X POST http://localhost:8000/v1/auth/register \
  -H "Content-Type: application/json" \
  -d '{"email": "admin@example.com", "password": "yourpassword", "org_name": "My Org"}'
```

The registration response includes the default project API key.

If the key is lost or exposed, rotate it with the Project API:

```bash
curl -X POST http://localhost:8000/v1/projects/YOUR_PROJECT_ID/rotate-key \
  -H "Authorization: Bearer YOUR_JWT_TOKEN"
```

The rotation response returns the replacement key once.

Admins can control sensitive payload storage in Project Settings. Large
input/output payload objects can be stored for all spans, only failed spans, or
not stored at all. The same section also sets the maximum stored payload size
and comma-separated field names that are redacted before any S3/MinIO write.
Trace Detail shows span-level payload storage status when payloads are loaded,
including policy omissions, oversized payloads and object-storage failures,
without storing prompt or output content in status fields.

For operational procedures after the first launch, see
[docs/runbooks.md](docs/runbooks.md). It covers local development, production
Docker Compose, environment variables, migrations, upgrades, rollbacks and
post-deploy smoke checks. Backup and restore procedures live in
[docs/backup-restore.md](docs/backup-restore.md).

Product and integration documentation:

- [Architecture](docs/architecture.md)
- [Browser token storage decision](docs/browser-token-storage.md)
- [Audit regression coverage](docs/audit-regression-coverage.md)
- [SDK integration guide](docs/sdk-integration.md)
- [Troubleshooting](docs/troubleshooting.md)
- [Roadmap and known limitations](docs/roadmap.md)

---

## SDK Integration

### Install

```bash
pip install llm-obs-sdk
```

The SDK package name is reserved for published releases. For local development,
install it from this repository:

```bash
cd sdk
pip install -e .
```

Full SDK examples live in [sdk/README.md](sdk/README.md) and the public
integration guide is in [docs/sdk-integration.md](docs/sdk-integration.md).

### Basic usage — decorator

```python
import asyncio
import llm_obs

@llm_obs.trace(name="my.llm_call")
async def call_llm(prompt: str) -> str:
    await asyncio.sleep(0.05)
    return "demo response"

async def main() -> None:
    await call_llm("Hello")
    await llm_obs.shutdown()

asyncio.run(main())
```

Set environment variables:

```bash
LLM_OBS_API_KEY=llmobs_your_key_here
LLM_OBS_ENDPOINT=http://your-llm-obs-host:8000
```

The SDK auto-initializes from environment variables — no explicit `init()` call needed.

Run a safe local smoke example without external LLM provider credentials:

```bash
export LLM_OBS_API_KEY=llmobs_your_key_here
export LLM_OBS_ENDPOINT=http://localhost:8000
python examples/sdk_smoke_demo.py
```

### Shutdown

Long-running applications can leave the SDK running in the background. In tests,
short-lived scripts or CLIs, shut it down before process exit so buffered spans
are flushed and the HTTP client is closed:

```python
import llm_obs

await llm_obs.shutdown()
```

Use `await llm_obs.shutdown(flush=False)` in tests that should discard buffered
spans instead of sending them. Failed flush attempts keep spans in memory for
the lifetime of that tracer rather than treating them as delivered.

### OpenAI auto-patching

```python
import openai
from llm_obs.integrations.openai import patch_openai

client = openai.AsyncOpenAI(api_key="...")
client = patch_openai(client)

# All calls are now automatically traced
response = await client.chat.completions.create(
    model="gpt-4o",
    messages=[{"role": "user", "content": "Hello"}]
)
```

### Anthropic auto-patching

```python
import anthropic
from llm_obs.integrations.anthropic import patch_anthropic

client = anthropic.AsyncAnthropic(api_key="...")
client = patch_anthropic(client)
```

### SDK troubleshooting

- No spans: check `LLM_OBS_API_KEY`, `LLM_OBS_ENDPOINT`, dashboard time range
  and `await llm_obs.shutdown()` in short-lived scripts.
- Auth failed: use a project ingest API key, not a login JWT token. Rotate the
  key in Project Settings if it was lost or exposed.
- Wrong endpoint: use `http://localhost:8000` from the host, or
  `http://backend:8000` from another Docker Compose service.
- Process exits before flush: end scripts, CLIs and tests with
  `await llm_obs.shutdown()`.

---

## Ingestion Failure Diagnostics

Accepted ingest batches return a `batch_id` immediately. Check asynchronous
processing status with the project API key:

Repeated ingest requests with the same `idempotency_key` and identical spans
return the original `batch_id` without enqueueing another batch. Reusing the
same idempotency key with a different request body returns `409 Conflict`.
Batch status `processed` counts spans actually inserted into storage; it can be
lower than `accepted` when duplicate span ids are ignored.
For the precise delivery contract, including client timeouts, worker retries,
idempotency and outbox backlog behavior, see
[docs/delivery-guarantees.md](docs/delivery-guarantees.md).

```bash
curl -H "X-API-Key: YOUR_PROJECT_API_KEY" \
  http://localhost:8000/v1/ingest/batches/YOUR_BATCH_ID
```

If a worker task fails permanently, admin users can inspect scoped failed-task
summaries with a JWT token:

```bash
curl -H "Authorization: Bearer YOUR_JWT_TOKEN" \
  "http://localhost:8000/v1/failed-tasks?project_id=YOUR_PROJECT_ID"
```

Mark an investigated task as resolved:

```bash
curl -X POST -H "Authorization: Bearer YOUR_JWT_TOKEN" \
  http://localhost:8000/v1/failed-tasks/FAILED_TASK_ID/resolve
```

Failed-task records store task metadata, batch/project identifiers, span counts,
error text and attempt count. They do not store full span payloads, prompts,
outputs or provider credentials.

---

## Pipeline Metrics

Prometheus metrics are exposed by the backend at `/metrics`. The ingest pipeline
publishes stable counters and histograms for batch and worker visibility:

- `llmobs_ingest_batches_accepted_total`
- `llmobs_ingest_batches_processed_total{status="processed|partial_failed"}`
- `llmobs_ingest_batches_failed_total{stage="enqueue|worker"}`
- `llmobs_ingest_batch_processing_seconds`
- `llmobs_ingest_spans_dropped_total{reason="processing_error"}`
- `llmobs_spans_ingested_total{provider,model,status}`

Check backend dependencies with `/ready`. Worker and scheduler liveness is
visible through `/worker-health`: the scheduler enqueues a lightweight
heartbeat task every minute, and the worker updates a Redis timestamp when it
executes that task. The endpoint returns `503` when the heartbeat is missing or
older than the configured threshold.

```bash
curl http://localhost:8000/ready
curl http://localhost:8000/worker-health
curl http://localhost:8000/metrics | grep llmobs_ingest
```

For public self-hosted deployments, terminate TLS in a reverse proxy in front of
Compose. Route the dashboard host to frontend port `3000`, route API and health
paths to backend port `8000`, and set `CORS_ALLOWED_ORIGINS` to the public
dashboard origin. Production Compose binds these host ports to `127.0.0.1` by
default; expose `/ready`, `/worker-health` and `/metrics` only to trusted
operators or monitoring systems.

---

## Configuration

Copy `backend/.env.prod.example` to `backend/.env.prod` and fill in the values.
For `infra/docker-compose.prod.yml`, keep database, PostgreSQL and MinIO
credentials consistent between `backend/.env.prod` and `infra/.env`.
Production startup validation rejects localhost service URLs, wildcard or
localhost CORS origins, empty secrets, default MinIO credentials and unedited
`replace-with...` placeholders.

| Variable | Description | Required |
|----------|-------------|----------|
| `SECRET_KEY` | Random 32+ char secret for JWT signing | ✅ |
| `DATABASE_URL` | Runtime PostgreSQL connection string using the dedicated app role | ✅ |
| `MIGRATION_DATABASE_URL` | Owner/admin PostgreSQL connection string used by Alembic migrations | recommended |
| `REDIS_URL` | Redis cache/pubsub/rate-limit connection string | ✅ |
| `REDIS_QUEUE_URL` | Durable Redis connection string for Taskiq queues and task results | ✅ |
| `AWS_ACCESS_KEY_ID` | MinIO or S3 access key | ✅ |
| `AWS_SECRET_ACCESS_KEY` | MinIO or S3 secret key | ✅ |
| `SMTP_HOST` | SMTP server for email alerts | optional |
| `SMTP_PORT` | SMTP port (default: 1025) | optional |
| `SMTP_FROM` | From address for alerts | optional |

---

## Model Pricing

After deployment, add pricing for your models so cost tracking works. Admin
users can manage prices in the dashboard Pricing page. Pricing records are
historical: adding a new price for the same provider/model closes the previous
active interval at the new `valid_from` timestamp.
Cost calculation cache keys include the span timestamp used for the historical
lookup, and pricing edits clear cached entries for that provider/model.

Pricing is also available through the API:

```bash
curl -H "Authorization: Bearer YOUR_JWT_TOKEN" \
  http://localhost:8000/v1/pricing

curl -X POST http://localhost:8000/v1/pricing \
  -H "Authorization: Bearer YOUR_JWT_TOKEN" \
  -H "Content-Type: application/json" \
  -d '{
    "provider": "openai",
    "model": "gpt-4o-mini",
    "input_cost_per_1k_tokens": 0.00015,
    "output_cost_per_1k_tokens": 0.0006
  }'
```

---

## Alerts

Create an alert rule via API:

```bash
curl -X POST http://localhost:8000/v1/alerts/rules \
  -H "Authorization: Bearer YOUR_JWT_TOKEN" \
  -H "Content-Type: application/json" \
  -d '{
    "project_id": "YOUR_PROJECT_ID",
    "name": "High Latency",
    "metric": "latency_p95",
    "condition": "gt",
    "threshold": 5000,
    "notify_email": "team@example.com"
  }'
```

Available metrics: `latency_p95`, `error_rate`, `cost_hourly`, `anomaly`.
`latency_p95`, `error_rate` and `cost_hourly` are evaluated over the rule's
`window_minutes`; `anomaly` uses the SDK/backend anomaly detectors for incoming
spans.

For Slack notifications add `notify_slack_webhook` with your Slack incoming webhook URL.
Alert rule reads and mutations are scoped to the selected `project_id`.

---

## Architecture

See [docs/architecture.md](docs/architecture.md) for the service map, ingest
flow, storage boundaries, dashboard APIs and operational components.

---

## Development

```bash
# Clone
git clone https://github.com/makel0ve/llm-obs
cd llm-obs

# Copy local development environment variables
cp backend/.env.example backend/.env

# Start the full local stack
docker compose -f infra/docker-compose.yml up -d

docker compose -f infra/docker-compose.yml exec backend alembic upgrade head
```

The backend, frontend, worker, PostgreSQL, Redis, MinIO and Mailpit are started
by the compose file.

For local code-only runs outside Docker, point `backend/.env` to host ports
first:

```bash
DATABASE_URL=postgresql+asyncpg://llmobs:llmobs_dev@localhost:5432/llmobs
REDIS_URL=redis://localhost:6379/0
S3_ENDPOINT_URL=http://localhost:9000

# Backend
cd backend
pip install -e ".[test]"
alembic upgrade head
uvicorn app.main:app --reload

# Frontend
cd frontend
npm install
npm run dev
```

### Tests

```bash
# Run backend integration tests
docker compose -f infra/docker-compose.yml run --rm backend pytest tests/ -v

# Run SDK tests
cd sdk && pytest llm_obs_tests/ -q

# Type checking
mypy backend/
mypy sdk/llm_obs

# Linting
ruff check .

# Frontend validation
cd frontend && npm run lint
cd frontend && npm run build
```

The frontend currently has no `npm test` script or component test runner. Do
not add a new frontend testing stack casually; add one as a dedicated decision
when component coverage becomes part of the release scope.

### Load testing

```bash
docker compose -f infra/docker-compose.yml run --rm \
  backend locust -f tests/load/locustfile.py \
  --host http://backend:8000 \
  --users 10 --spawn-rate 2 --run-time 60s --headless --only-summary
```

---

## Stack

| Component | Technology |
|-----------|------------|
| Backend | Python 3.11+, FastAPI, SQLAlchemy async |
| Database | PostgreSQL 16 with pgvector, PgBouncer |
| Queue | Redis 7, Taskiq |
| Storage | MinIO (S3-compatible) |
| Frontend | React, TypeScript, Vite, Tailwind CSS |
| Infra | Docker Compose, experimental Helm manifests |

---

## Current Dashboard Scope

The current frontend includes account creation/sign-in, invite acceptance,
overview metrics and charts, trace listing/detail pages, alert rule/event
management, pricing records, user and role management, audit log, project
settings, payload privacy controls, legacy key rotation, managed API keys and
onboarding empty states for new projects.

Dashboard API calls are routed through typed frontend helpers in
`frontend/src/api/dashboard.ts`. Authentication failures from protected API
routes clear the local session and return the user to sign-in; auth endpoints
handle their own errors without triggering that redirect.

---

## Roadmap and Limitations

Current limitations and planned work are tracked in
[docs/roadmap.md](docs/roadmap.md). The short version: the dashboard works with
one active project per login session, frontend component tests are not
configured yet, and Helm manifests are still experimental.

---

## Contributing

1. Fork the repository
2. Create a feature branch: `git checkout -b feat/your-feature`
3. Make your changes following [Conventional Commits](https://www.conventionalcommits.org/)
4. Run backend tests: `pytest tests/ -v`
5. Run SDK tests: `cd sdk && pytest llm_obs_tests/ -q`
6. Run linting and type checks: `ruff check . && mypy backend/ && mypy sdk/llm_obs`
7. Submit a pull request

See [CONTRIBUTING.md](CONTRIBUTING.md) for detailed setup instructions.

---

## Security

To report a security vulnerability please email security@llm-obs.io. We will respond within 48 hours. See [SECURITY.md](SECURITY.md).

---

## License

MIT — see [LICENSE](LICENSE)
