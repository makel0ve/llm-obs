# LLM Obs Runbooks

Operational notes for local development and self-hosted Docker Compose
deployments. Commands assume they are run from the repository root.

For database and payload backups, restore order, and post-restore checks, see
[backup-restore.md](backup-restore.md).

## Local Development

Create the backend environment file:

```bash
cp backend/.env.example backend/.env
```

Start the full local stack:

```bash
docker compose -f infra/docker-compose.yml up -d
docker compose -f infra/docker-compose.yml exec backend alembic upgrade head
```

Open:

- Dashboard: <http://localhost:3000>
- Backend API: <http://localhost:8000>
- Mailpit: <http://localhost:8025>
- MinIO console: <http://localhost:9001>

Stop local services without deleting volumes:

```bash
docker compose -f infra/docker-compose.yml down
```

For code-only backend/frontend runs outside Docker, keep Postgres, Redis and
MinIO running through the local compose file, then point `backend/.env` at host
ports:

```bash
DATABASE_URL=postgresql+asyncpg://llmobs_app:llmobs_dev@localhost:5432/llmobs
MIGRATION_DATABASE_URL=postgresql+asyncpg://llmobs_owner:llmobs_owner_dev@localhost:5432/llmobs
REDIS_URL=redis://localhost:6379/0
REDIS_QUEUE_URL=redis://localhost:6380/0
S3_ENDPOINT_URL=http://localhost:9000
```

Run backend:

```bash
cd backend
pip install -e ".[test]"
alembic upgrade head
uvicorn app.main:app --reload
```

Run frontend:

```bash
cd frontend
npm install
npm run dev
```

## Production Docker Compose

Production compose uses:

- `infra/docker-compose.prod.yml`
- `infra/.env`
- `backend/.env.prod`

Create the files:

```bash
cp infra/.env.example infra/.env
cp backend/.env.prod.example backend/.env.prod
```

Generate a production secret:

```bash
python3 -c "import secrets; print(secrets.token_hex(32))"
```

Set `ENVIRONMENT=production` in `backend/.env.prod`.
Startup validation rejects common unsafe production values, including localhost
service URLs, wildcard or localhost CORS origins, empty secrets, default MinIO
credentials and unedited `replace-with...` placeholders.

For the production compose file, the backend should connect through PgBouncer:

```bash
DATABASE_URL=postgresql+asyncpg://POSTGRES_APP_USER:POSTGRES_APP_PASSWORD@pgbouncer:6432/POSTGRES_DB
MIGRATION_DATABASE_URL=postgresql+asyncpg://POSTGRES_USER:POSTGRES_PASSWORD@postgres:5432/POSTGRES_DB
```

Use real values in the URL. Keep `POSTGRES_DB`, `POSTGRES_USER`,
`POSTGRES_PASSWORD`, `POSTGRES_APP_USER`, `POSTGRES_APP_PASSWORD`,
`MINIO_ROOT_USER` and `MINIO_ROOT_PASSWORD` consistent between `infra/.env` and
`backend/.env.prod`.

For tenant isolation, the runtime role used by `DATABASE_URL` must not be a
PostgreSQL superuser and must not have `BYPASSRLS`. `FORCE ROW LEVEL SECURITY`
does not protect rows from superuser or `BYPASSRLS` roles. If a deployment uses
a bootstrap/admin Postgres role to initialize the database, create a separate
application role for `DATABASE_URL` before accepting tenant data.

For new Docker volumes, the compose Postgres init script creates or updates
`POSTGRES_APP_USER` with `NOSUPERUSER NOBYPASSRLS` and grants schema/default
privileges. Existing volumes do not rerun init scripts, so run migrations with
`MIGRATION_DATABASE_URL` set and `POSTGRES_APP_USER`/`POSTGRES_APP_PASSWORD`
available before switching runtime traffic to the app role.

Validate compose configuration before starting:

```bash
docker compose -f infra/docker-compose.yml config
docker compose --env-file infra/.env -f infra/docker-compose.prod.yml config
```

Build and start production services:

```bash
docker compose --env-file infra/.env -f infra/docker-compose.prod.yml up -d --build
```

Apply database migrations:

```bash
docker compose --env-file infra/.env -f infra/docker-compose.prod.yml exec backend alembic upgrade head
```

Check service status and logs:

```bash
docker compose --env-file infra/.env -f infra/docker-compose.prod.yml ps
docker compose --env-file infra/.env -f infra/docker-compose.prod.yml logs --tail=100 backend
docker compose --env-file infra/.env -f infra/docker-compose.prod.yml logs --tail=100 worker
docker compose --env-file infra/.env -f infra/docker-compose.prod.yml logs --tail=100 scheduler
```

The scheduler runs retention cleanup daily. Retention deletes old span payload
objects only under the owning project's `payloads/{project_id}/` prefix, then
deletes matching old spans in batches and removes trace rows that no longer
have spans. If object deletion fails, the affected span rows are left for the
next retry instead of orphaning payload objects.

Production Compose exposes backend port `8000` and frontend port `3000` on the
host. Put a reverse proxy in front of those ports for public deployments. The
application containers do not terminate TLS themselves.

Minimum reverse proxy assumptions:

- terminate TLS at the proxy and forward plain HTTP to Compose services;
- route the dashboard host to frontend port `3000`;
- route API paths such as `/v1`, `/ready`, `/health`, `/worker-health` and
  `/metrics` to backend port `8000`;
- forward `Host`, `X-Forwarded-Proto` and client IP headers if the proxy
  supports them;
- set `CORS_ALLOWED_ORIGINS` in `backend/.env.prod` to the public dashboard
  origin, for example `https://obs.example.com`;
- keep backend, Postgres, Redis, Redis queue, PgBouncer and MinIO ports private
  unless there is an explicit operational need to expose them.

## Environment Variables

Backend settings are loaded from `backend/.env.prod` in production.

| Variable | Purpose | Production notes |
| --- | --- | --- |
| `ENVIRONMENT` | Runtime mode | Set to `production`. |
| `SECRET_KEY` | JWT signing secret | Use a random 32+ character value. |
| `DATABASE_URL` | Runtime SQLAlchemy async URL | Use `POSTGRES_APP_USER` through PgBouncer at `pgbouncer:6432` in production compose. The role must not be superuser, table owner or `BYPASSRLS`. |
| `MIGRATION_DATABASE_URL` | Alembic SQLAlchemy async URL | Use the owner/admin role directly against `postgres:5432` for migrations and grants. If omitted, Alembic falls back to `DATABASE_URL`. |
| `DATABASE_POOL_SIZE` | Backend DB pool size | Keep conservative when using PgBouncer. |
| `DATABASE_MAX_OVERFLOW` | Backend DB overflow connections | Keep conservative when using PgBouncer. |
| `REDIS_URL` | Redis cache/pubsub/rate-limit URL | Use `redis://redis:6379/0` in compose. This Redis may use bounded memory and cache eviction. |
| `REDIS_QUEUE_URL` | Durable Taskiq queue/result URL | Use `redis://redis-queue:6379/0` in compose. This Redis must use persistent storage and `noeviction`; if omitted, Taskiq falls back to `REDIS_URL`. |
| `JWT_ALGORITHM` | JWT algorithm | Default `HS256`. |
| `JWT_ACCESS_TOKEN_EXPIRE_MINUTES` | Login token lifetime | Default `1440`. |
| `API_RATE_LIMIT_PER_MINUTE` | API rate limit | Tune per deployment. |
| `CORS_ALLOWED_ORIGINS` | Dashboard origins | Set the public dashboard origin, comma-separated if multiple. |
| `S3_BUCKET` | Payload bucket | Default `llm-obs-payloads`. |
| `S3_ENDPOINT_URL` | S3-compatible endpoint | Use `http://minio:9000` for compose MinIO. |
| `AWS_ACCESS_KEY_ID` | S3/MinIO access key | Keep secret. |
| `AWS_SECRET_ACCESS_KEY` | S3/MinIO secret key | Keep secret. |
| `DEFAULT_RETENTION_DAYS` | Default project retention | Default `90`. |
| `SMTP_HOST` | SMTP host for alerts | Use Mailpit locally or a real SMTP host in production. |
| `SMTP_PORT` | SMTP port | Default local value is `1025`. |
| `SMTP_USER` | SMTP username | Optional if server does not require auth. |
| `SMTP_PASSWORD` | SMTP password | Keep secret. |
| `SMTP_FROM` | Alert sender address | Use a verified sender for production SMTP. |

The production compose file also reads these from `infra/.env` for Postgres and
MinIO container bootstrap:

| Variable | Purpose |
| --- | --- |
| `POSTGRES_DB` | Initial database name |
| `POSTGRES_USER` | Database user |
| `POSTGRES_PASSWORD` | Database password |
| `POSTGRES_APP_USER` | Runtime application database user |
| `POSTGRES_APP_PASSWORD` | Runtime application database password |
| `POSTGRES_HOST` | PgBouncer upstream host, normally `postgres` |
| `POSTGRES_PORT` | PgBouncer upstream port, normally `5432` |
| `MINIO_ROOT_USER` | MinIO root user |
| `MINIO_ROOT_PASSWORD` | MinIO root password |

## Migrations

Check the current Alembic head:

```bash
docker compose --env-file infra/.env -f infra/docker-compose.prod.yml exec backend alembic current
docker compose --env-file infra/.env -f infra/docker-compose.prod.yml exec backend alembic heads
```

Apply migrations:

```bash
docker compose --env-file infra/.env -f infra/docker-compose.prod.yml exec backend alembic upgrade head
```

For local development:

```bash
docker compose -f infra/docker-compose.yml exec backend alembic upgrade head
```

Database rollback must be planned per migration. Only use `alembic downgrade`
after verifying the target migration has a safe downgrade path and after taking
a database backup. For production incidents, prefer restoring from a known-good
backup when schema changes are involved.

## Upgrade Flow

1. Read release notes and identify whether migrations are included.
2. Take a database backup before schema changes.
3. Pull the target revision:

```bash
git fetch origin
git switch main
git pull --ff-only origin main
```

4. Validate production compose config:

```bash
docker compose --env-file infra/.env -f infra/docker-compose.prod.yml config
```

5. Build and start updated containers:

```bash
docker compose --env-file infra/.env -f infra/docker-compose.prod.yml up -d --build
```

6. Apply migrations:

```bash
docker compose --env-file infra/.env -f infra/docker-compose.prod.yml exec backend alembic upgrade head
```

7. Run smoke checks.

## Rollback Flow

Code/container rollback is safe only if the database schema remains compatible
with the previous version.

1. Identify the previous known-good git revision or release tag.
2. Check it out for deployment:

```bash
git switch --detach PREVIOUS_GOOD_REVISION
```

3. Rebuild and restart:

```bash
docker compose --env-file infra/.env -f infra/docker-compose.prod.yml up -d --build
```

4. Run smoke checks.

If the upgrade included migrations, do not assume code rollback is enough.
Either run a verified Alembic downgrade for the specific migration or restore
Postgres from backup. Do not delete Docker volumes as a rollback shortcut.

## Smoke Checks

Check containers:

```bash
docker compose --env-file infra/.env -f infra/docker-compose.prod.yml ps
```

Check backend liveness, dependency readiness and worker/scheduler heartbeat:

```bash
curl -f http://localhost:8000/health
curl -f http://localhost:8000/ready
curl -f http://localhost:8000/worker-health
```

`/health` only proves the backend process can serve HTTP. `/ready` verifies
Postgres and Redis. `/worker-health` verifies that the scheduler enqueued the
heartbeat task and a worker wrote it to Redis.

The Compose files separate Redis responsibilities. `redis` handles cache,
rate-limit counters, batch status and live pub/sub. `redis-queue` handles
Taskiq queues, task results and the DLQ with AOF persistence and `noeviction`,
so accepted ingest work is not subject to cache eviction.

`/worker-health` depends on the scheduler and worker services. The scheduler
enqueues a lightweight heartbeat task every minute, and the worker updates the
heartbeat timestamp in Redis. A `503` response with `missing` means no
heartbeat has been recorded yet; `stale` means the worker/scheduler path has not
completed a heartbeat within the configured age threshold.

If `/worker-health` is `missing` or `stale`, inspect both services:

```bash
docker compose --env-file infra/.env -f infra/docker-compose.prod.yml logs --tail=100 scheduler
docker compose --env-file infra/.env -f infra/docker-compose.prod.yml logs --tail=100 worker
```

Check the runtime role before accepting tenant data:

```bash
docker compose --env-file infra/.env -f infra/docker-compose.prod.yml exec postgres \
  psql -U "$POSTGRES_USER" -d "$POSTGRES_DB" \
  -c "SELECT rolname, rolsuper, rolbypassrls FROM pg_roles WHERE rolname IN ('$POSTGRES_USER', '$POSTGRES_APP_USER');"
```

`POSTGRES_APP_USER` must show `rolsuper = false` and `rolbypassrls = false`.

Check Prometheus metrics:

```bash
curl -f http://localhost:8000/metrics | grep llmobs_ingest
```

Create or verify a login through the dashboard at <http://localhost:3000>.

Register a first admin user if this is a fresh deployment:

```bash
curl -X POST http://localhost:8000/v1/auth/register \
  -H "Content-Type: application/json" \
  -d '{"email":"admin@example.com","password":"change-me-now","org_name":"My Org"}'
```

Save the one-time project API key from the response. Send one SDK smoke span:

```bash
LLM_OBS_API_KEY=llmobs_your_key_here \
LLM_OBS_ENDPOINT=http://localhost:8000 \
python examples/sdk_smoke_demo.py
```

Expected result:

- `/ready` returns success.
- `/worker-health` returns success after the first scheduled heartbeat.
- Dashboard opens.
- Overview and Traces load without authentication loops.
- The smoke span appears in Traces for the selected time range.
- Worker logs have no repeated processing failures.
