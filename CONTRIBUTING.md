# Contributing to LLM Obs

Thank you for your interest in contributing! This document explains how to get started.

---

## Development Setup

```bash
git clone https://github.com/makel0ve/llm-obs
cd llm-obs

# Copy environment files
cp backend/.env.example backend/.env
cp infra/.env.example infra/.env

# Start dev infrastructure
docker compose -f infra/docker-compose.yml up -d

# Install backend dependencies
cd backend
pip install -e ".[test,dev]"

# Apply migrations
alembic upgrade head

# Start backend
uvicorn app.main:app --reload
```

```bash
# Start frontend
cd frontend
npm install
npm run dev
```

---

## Running Tests

```bash
# Integration tests (requires running postgres and redis)
docker compose -f infra/docker-compose.yml run --rm backend pytest tests/ -v

# With coverage
docker compose -f infra/docker-compose.yml run --rm backend pytest tests/ -v --cov=app

# Type checking
mypy backend/

# Linting
ruff check .
ruff format .
```

---

## Conventional Commits

All commits must follow [Conventional Commits](https://www.conventionalcommits.org/):

| Prefix | When to use |
|--------|-------------|
| `feat:` | New feature |
| `fix:` | Bug fix |
| `perf:` | Performance improvement |
| `docs:` | Documentation only |
| `test:` | Adding or fixing tests |
| `refactor:` | Code refactoring without behavior change |
| `chore:` | Maintenance, dependencies, tooling |

Examples:
```
feat: add Slack webhook notifications
fix: correct latency_p95 alert threshold comparison
docs: update SDK integration examples
```

---

## Pull Request Process

1. Fork the repository and create a branch from `main`
2. Branch name should describe the change: `feat/slack-alerts`, `fix/alert-threshold`
3. Make sure tests pass and there are no linting errors
4. Write a clear PR description explaining what and why
5. Reference any related issues: `Closes #123`

---

## Project Structure

```
llm-obs/
├── sdk/                    # Python SDK
│   └── llm_obs/
│       ├── __init__.py     # auto-init from env
│       ├── tracer.py       # LLMTracer, SpanData
│       ├── decorators.py   # @trace decorator
│       ├── transport.py    # HTTP transport
│       └── integrations/   # OpenAI, Anthropic patches
├── backend/
│   ├── app/
│   │   ├── api/v1/         # FastAPI routers
│   │   ├── core/           # config, db, redis, auth
│   │   ├── models/         # SQLAlchemy models
│   │   ├── schemas/        # Pydantic schemas
│   │   ├── services/       # business logic
│   │   └── workers/        # Taskiq tasks
│   ├── alembic/            # database migrations
│   ├── tests/
│   │   ├── integration/    # integration tests
│   │   ├── load/           # locust load tests
│   │   └── factories.py    # test fixtures
│   └── seed/               # dev seed data
├── frontend/               # React + Vite dashboard
└── infra/                  # Docker Compose configs
```

---

## Adding a New Feature

1. **Backend endpoint** — add router in `app/api/v1/`, schema in `app/schemas/`, service logic in `app/services/`
2. **Database changes** — create a migration: `alembic revision --autogenerate -m "description"`
3. **Tests** — add integration tests in `tests/integration/`
4. **Frontend** — update `frontend/src/api/client.ts` and relevant pages

---

## Reporting Bugs

Open a GitHub issue with:
- Description of the bug
- Steps to reproduce
- Expected vs actual behavior
- Environment (OS, Docker version, Python version)

---

## Security Vulnerabilities

Please do **not** open a public issue for security vulnerabilities. Email security@llm-obs.io instead. See [SECURITY.md](SECURITY.md).
