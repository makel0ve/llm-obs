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
- **Self-hosted** — Docker Compose or Kubernetes (Helm)

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

The first registration response includes the default project API key. Save it:
it is shown only once.

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

### Basic usage — decorator

```python
from llm_obs import trace

@trace(name="my.llm_call")
async def call_llm(prompt: str) -> str:
    # your LLM call here
    ...
```

Set environment variables:

```bash
LLM_OBS_API_KEY=llmobs_your_key_here
LLM_OBS_ENDPOINT=http://your-llm-obs-host:8000
```

The SDK auto-initializes from environment variables — no explicit `init()` call needed.

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

After deployment, add pricing for your models so cost tracking works:

```sql
INSERT INTO model_pricing (provider, model, input_cost_per_1k_tokens, output_cost_per_1k_tokens, valid_from)
VALUES
    ('openai',    'gpt-4o',            0.0025,   0.0100,   NOW()),
    ('openai',    'gpt-4o-mini',       0.000150, 0.000600, NOW()),
    ('anthropic', 'claude-sonnet-4-6', 0.003,    0.015,    NOW()),
    ('ollama',    'llama3.2:3b',       0.0,      0.0,      NOW());
```

Connect to the database:

```bash
docker compose --env-file infra/.env -f infra/docker-compose.prod.yml exec postgres psql -U llmobs -d llmobs
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
# Run integration tests
docker compose -f infra/docker-compose.yml run --rm backend pytest tests/ -v

# Type checking
mypy backend/

# Linting
ruff check .
```

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
| Infra | Docker Compose, Helm (Kubernetes) |

---

## Current Dashboard Scope

The current frontend includes login and overview metrics for a project. Trace
listing/detail views, alert management screens and project settings are available
through backend APIs but are not yet exposed as full dashboard pages.

---

## Known Limitations (v1)

- Registration is available via API only (no UI form yet)
- Dashboard shows one project per login session (multi-project selector coming in v2)
- Model pricing must be configured via SQL (admin UI coming in v2)
- Dead Letter Queue is implemented but not automatically connected to retry middleware
- OpenAI and Anthropic integration tests require real API keys

---

## Roadmap (v2)

- [ ] Registration and user management UI
- [ ] Multi-project selector in dashboard
- [ ] Admin UI for model pricing
- [ ] DLQ integration with retry middleware
- [ ] Trace waterfall visualization in frontend
- [ ] SDK tests with mocked providers
- [ ] Kubernetes Helm chart

---

## Contributing

1. Fork the repository
2. Create a feature branch: `git checkout -b feat/your-feature`
3. Make your changes following [Conventional Commits](https://www.conventionalcommits.org/)
4. Run tests: `pytest tests/ -v`
5. Run linting: `ruff check . && mypy backend/`
6. Submit a pull request

See [CONTRIBUTING.md](CONTRIBUTING.md) for detailed setup instructions.

---

## Security

To report a security vulnerability please email security@llm-obs.io. We will respond within 48 hours. See [SECURITY.md](SECURITY.md).

---

## License

MIT — see [LICENSE](LICENSE)
