# LLM Obs — Self-hosted LLM Observability

Track costs, latency, errors and anomalies for every LLM call.
Open-source, privacy-first alternative to LangSmith and Helicone.

![Dashboard](docs/assets/dashboard.png)

---

## What is LLM Obs?

LLM Obs is a self-hosted platform for monitoring LLM calls. Your data never leaves your infrastructure. Deploy it once, connect your Python projects in minutes.

---

## Features

- **Python SDK** — `@trace` decorator and auto-patching for OpenAI, Anthropic
- **Cost tracking** — per model, per project, with historical pricing support
- **Latency metrics** — average, P95 and P99 with time series charts
- **Trace API** — query traces and spans, with optional stored input/output payloads
- **Alerts API** — email and Slack notifications with configurable thresholds
- **OpenTelemetry** — OTLP HTTP endpoint for existing instrumentation
- **Multi-tenant** — organizations, projects, API keys
- **Data retention** — automatic cleanup with per-project policies
- **Self-hosted** — Docker Compose, with experimental Helm manifests

---

## Quick Start

```bash
git clone https://github.com/makel0ve/llm-obs
cd llm-obs

# Copy and fill in environment variables
cp backend/.env.example backend/.env.prod
cp infra/.env.example infra/.env

# Generate SECRET_KEY
python3 -c "import secrets; print(secrets.token_hex(32))"

# In backend/.env.prod, set ENVIRONMENT=production and use PgBouncer:
# DATABASE_URL=postgresql+asyncpg://<POSTGRES_USER>:<POSTGRES_PASSWORD>@pgbouncer:6432/<POSTGRES_DB>

# Start
docker compose --env-file infra/.env -f infra/docker-compose.prod.yml up -d

# Apply migrations
docker compose --env-file infra/.env -f infra/docker-compose.prod.yml exec backend alembic upgrade head

# Create first user
curl -X POST http://localhost:8000/v1/auth/register \
  -H "Content-Type: application/json" \
  -d '{"email": "admin@example.com", "password": "yourpassword", "org_name": "My Org"}'

# Open dashboard
open http://localhost:3000
```

The first registration response includes the default project API key. The
dashboard Create account flow shows the same key after signup. Save it before
dismissing or refreshing the page: API keys are shown only once.

If the key is lost or exposed, rotate it with the Project API:

```bash
curl -X POST http://localhost:8000/v1/projects/YOUR_PROJECT_ID/rotate-key \
  -H "Authorization: Bearer YOUR_JWT_TOKEN"
```

The rotation response returns the replacement key once.

For operational procedures after the first launch, see
[docs/runbooks.md](docs/runbooks.md). It covers local development, production
Docker Compose, environment variables, migrations, upgrades, rollbacks and
post-deploy smoke checks. Backup and restore procedures live in
[docs/backup-restore.md](docs/backup-restore.md).

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

Full SDK examples and troubleshooting live in [sdk/README.md](sdk/README.md).

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

Check backend dependencies with `/ready`; worker processing health is visible
through the batch status API, failed task API and the metrics above.

```bash
curl http://localhost:8000/ready
curl http://localhost:8000/metrics | grep llmobs_ingest
```

---

## Configuration

Copy `backend/.env.example` to `backend/.env.prod` and fill in the values.
For `infra/docker-compose.prod.yml`, keep database, PostgreSQL and MinIO
credentials consistent between `backend/.env.prod` and `infra/.env`.

| Variable | Description | Required |
|----------|-------------|----------|
| `SECRET_KEY` | Random 32+ char secret for JWT signing | ✅ |
| `DATABASE_URL` | PostgreSQL connection string | ✅ |
| `REDIS_URL` | Redis connection string | ✅ |
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

For Slack notifications add `notify_slack_webhook` with your Slack incoming webhook URL.

---

## Architecture

```
SDK (Python)
    │  HTTP batch
    ▼
Ingest API (FastAPI)
    │  Redis queue
    ▼
Worker (Taskiq)
    ├── Process spans → PostgreSQL + MinIO (S3)
    ├── Update trace aggregates
    └── Check alert rules → Email / Slack

Dashboard (React + Vite)
    │  REST API
    ▼
Query API (FastAPI)
    └── PostgreSQL (with PgBouncer)

Scheduler (Taskiq)
    ├── Data retention (daily)
    └── Partition management (monthly)
```

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

The current frontend includes account creation/sign-in, overview metrics,
trace listing/detail pages, alert rule/event management, project settings,
API key rotation and onboarding empty states for new projects.

Dashboard API calls are routed through typed frontend helpers in
`frontend/src/api/dashboard.ts`. Authentication failures from protected API
routes clear the local session and return the user to sign-in; auth endpoints
handle their own errors without triggering that redirect.

---

## Known Limitations (v1)

- Dashboard shows one project per login session (multi-project selector coming in v2)
- Dead Letter Queue is implemented but not automatically connected to retry middleware
- Frontend component/unit tests are not configured yet
- OpenAI and Anthropic integration tests require real API keys

---

## Roadmap (v2)

- [ ] Registration and user management UI
- [ ] Multi-project selector in dashboard
- [ ] DLQ integration with retry middleware
- [ ] Trace waterfall visualization in frontend
- [ ] Provider integration tests with mocked OpenAI and Anthropic clients
- [ ] Production-ready Kubernetes Helm chart

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
