# Backup and Restore

This guide covers self-hosted Docker Compose deployments using
`infra/docker-compose.prod.yml`.

Commands assume they are run from the repository root. The variable-loading
snippets use `bash`; fish users can run the snippets through `bash` or export
the variables manually.

## What Must Be Backed Up

LLM Obs has two durable data stores:

- PostgreSQL volume `postgres_data`
- MinIO/S3 bucket from `S3_BUCKET`

PostgreSQL stores organizations, users, projects, API key hashes, traces, spans,
pricing, alerts, retention settings and S3 object keys. MinIO/S3 stores larger
payload objects referenced by those keys.

Back up Postgres and MinIO/S3 from the same maintenance window. Restoring only
one side can leave trace rows pointing at missing payload objects, or leave
orphaned payload objects that the application no longer references.

## Prepare a Backup Directory

```bash
mkdir -p backups
```

For consistent backups, pause services that can write spans or settings:

```bash
docker compose --env-file infra/.env -f infra/docker-compose.prod.yml stop backend worker scheduler
```

Keep `postgres`, `minio`, `redis` and `pgbouncer` running while taking backups.

## PostgreSQL Backup

Create a compressed custom-format dump:

```bash
backup_ts=$(date -u +%Y%m%dT%H%M%SZ)
docker compose --env-file infra/.env -f infra/docker-compose.prod.yml exec -T postgres \
  sh -lc 'pg_dump -U "$POSTGRES_USER" -d "$POSTGRES_DB" -Fc' \
  > "backups/postgres_${backup_ts}.dump"
```

Verify that the dump is readable:

```bash
docker compose --env-file infra/.env -f infra/docker-compose.prod.yml exec -T postgres \
  sh -lc 'pg_restore --list' \
  < "backups/postgres_${backup_ts}.dump" \
  > "backups/postgres_${backup_ts}.manifest"
```

Restart paused services after the database and object-store backups are done:

```bash
docker compose --env-file infra/.env -f infra/docker-compose.prod.yml start backend worker scheduler
```

## PostgreSQL Restore

Stop services that write to the database:

```bash
docker compose --env-file infra/.env -f infra/docker-compose.prod.yml stop backend worker scheduler
```

Restore a dump into the configured database:

```bash
cat backups/postgres_YYYYMMDDTHHMMSSZ.dump | \
  docker compose --env-file infra/.env -f infra/docker-compose.prod.yml exec -T postgres \
    sh -lc 'pg_restore -U "$POSTGRES_USER" -d "$POSTGRES_DB" --clean --if-exists --no-owner'
```

If the restored dump is from an older application version and you are running a
newer code revision, apply migrations after restore:

```bash
docker compose --env-file infra/.env -f infra/docker-compose.prod.yml exec backend alembic upgrade head
```

Then start services and run smoke checks:

```bash
docker compose --env-file infra/.env -f infra/docker-compose.prod.yml start backend worker scheduler
```

## MinIO Backup

Load local env files into the shell for the `minio/mc` helper container:

```bash
set -a
. infra/.env
. backend/.env.prod
set +a
```

Mirror the configured bucket to a timestamped local directory:

```bash
backup_ts=$(date -u +%Y%m%dT%H%M%SZ)
bucket="${S3_BUCKET:-llm-obs-payloads}"

docker run --rm --network infra_default \
  -e MC_HOST_llmobs="http://${MINIO_ROOT_USER}:${MINIO_ROOT_PASSWORD}@minio:9000" \
  -v "$PWD/backups:/backups" \
  minio/mc mirror "llmobs/${bucket}" "/backups/minio_${backup_ts}/${bucket}"
```

For S3-compatible cloud storage, use the provider's native backup/versioning
tooling instead of the local MinIO helper container. The important requirement
is the same: preserve all objects referenced by `payload_s3_key` values in
PostgreSQL.

## MinIO Restore

Stop write-capable services:

```bash
docker compose --env-file infra/.env -f infra/docker-compose.prod.yml stop backend worker scheduler
```

Load env files:

```bash
set -a
. infra/.env
. backend/.env.prod
set +a
```

Restore the bucket from a matching backup directory:

```bash
bucket="${S3_BUCKET:-llm-obs-payloads}"

docker run --rm --network infra_default \
  -e MC_HOST_llmobs="http://${MINIO_ROOT_USER}:${MINIO_ROOT_PASSWORD}@minio:9000" \
  -v "$PWD/backups:/backups" \
  minio/mc mb --ignore-existing "llmobs/${bucket}"

docker run --rm --network infra_default \
  -e MC_HOST_llmobs="http://${MINIO_ROOT_USER}:${MINIO_ROOT_PASSWORD}@minio:9000" \
  -v "$PWD/backups:/backups" \
  minio/mc mirror --overwrite "/backups/minio_YYYYMMDDTHHMMSSZ/${bucket}" "llmobs/${bucket}"
```

Start services after PostgreSQL and MinIO have both been restored:

```bash
docker compose --env-file infra/.env -f infra/docker-compose.prod.yml start backend worker scheduler
```

## Full Restore Order

Use this order when restoring a whole deployment:

1. Check out the application version compatible with the backup.
2. Restore `infra/.env` and `backend/.env.prod` from your secret manager.
3. Start infra services:

```bash
docker compose --env-file infra/.env -f infra/docker-compose.prod.yml up -d postgres redis minio pgbouncer
```

4. Restore PostgreSQL.
5. Restore MinIO/S3 from the matching backup timestamp.
6. Start backend, worker, scheduler and frontend:

```bash
docker compose --env-file infra/.env -f infra/docker-compose.prod.yml up -d --build
```

7. Apply migrations only if the running code revision requires newer schema.
8. Run smoke checks.

## Secrets and Env Consistency

Do not store real secrets in Git.

Keep these values consistent with the restored data and object store:

- `DATABASE_URL`, `POSTGRES_DB`, `POSTGRES_USER`, `POSTGRES_PASSWORD`
- `S3_BUCKET`, `S3_ENDPOINT_URL`, `AWS_ACCESS_KEY_ID`, `AWS_SECRET_ACCESS_KEY`
- `MINIO_ROOT_USER`, `MINIO_ROOT_PASSWORD` for local MinIO
- `SECRET_KEY` for JWT signing
- `CORS_ALLOWED_ORIGINS` for the restored dashboard URL

Changing `SECRET_KEY` invalidates existing login tokens. Project ingest API keys
are stored as hashes; raw API keys cannot be recovered from a database backup.
If users lost raw keys, rotate them after restore.

Postgres backup without matching object-store backup can produce missing
payloads in Trace Detail. Object-store backup without matching Postgres backup
can produce orphaned objects. Keep backup timestamps together and label them as
a pair.

## Smoke Checks After Restore

Check containers:

```bash
docker compose --env-file infra/.env -f infra/docker-compose.prod.yml ps
```

Check backend health:

```bash
curl -f http://localhost:8000/health
curl -f http://localhost:8000/ready
```

Check migrations:

```bash
docker compose --env-file infra/.env -f infra/docker-compose.prod.yml exec backend alembic current
```

Open the dashboard and verify:

- Login works.
- Overview loads.
- Traces load for a period known to contain data.
- Trace Detail opens for a restored trace.
- Payload loading works for traces that had stored payloads.
- Project Settings shows the expected project id and retention.

Send a new smoke span after restore:

```bash
LLM_OBS_API_KEY=llmobs_your_key_here \
LLM_OBS_ENDPOINT=http://localhost:8000 \
python examples/sdk_smoke_demo.py
```

Check worker logs for processing errors:

```bash
docker compose --env-file infra/.env -f infra/docker-compose.prod.yml logs --tail=100 worker
```
