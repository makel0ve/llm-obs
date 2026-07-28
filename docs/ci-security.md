# CI Security Controls

## Runtime database role RLS

The backend CI `test` job runs database migrations with
`MIGRATION_DATABASE_URL` as the PostgreSQL owner role and runs application tests
with `DATABASE_URL` as the non-owner runtime role. The runtime role is created
by migrations from `POSTGRES_APP_USER` and `POSTGRES_APP_PASSWORD` and must be
`NOSUPERUSER NOBYPASSRLS`.

CI has a dedicated invariant gate:

```bash
cd backend && RUN_RUNTIME_RLS_TESTS=1 pytest tests/integration/test_runtime_role_rls.py -q
```

That test proves the runtime role cannot read trace/span rows without
`app.current_project_id`, can see only the selected project after the project
context is set, and that parent plus child trace/span partitions keep
`ENABLE/FORCE ROW LEVEL SECURITY`.

## E2E Compose smoke

CI runs an `e2e-compose` job against the local Docker Compose stack:

```bash
cp backend/.env.example backend/.env
docker compose -f infra/docker-compose.yml up -d --build postgres redis redis-queue minio backend worker
docker compose -f infra/docker-compose.yml exec -T backend alembic upgrade head
python -m pip install -e ./sdk
python scripts/e2e_compose_smoke.py
docker compose -f infra/docker-compose.yml down -v
```

CI creates `backend/.env` from `backend/.env.example` before starting Compose.
For a fresh local checkout, do the same if `backend/.env` does not exist.

The smoke registers an isolated organization, sends one real SDK span, sends
one direct ingest payload to verify batch status, waits for the worker to
persist both spans, then verifies trace visibility and MinIO-backed payload
retrieval/redaction through the Query API. It does not call external LLM
providers.

## Secret scanning

The `security` workflow job installs `detect-secrets==1.5.0` and runs:

```bash
git ls-files -z | xargs -0 detect-secrets-hook --baseline .secrets.baseline --no-verify
```

This scans tracked files only and compares findings against the committed
baseline. `detect-secrets` stores hashed findings in `.secrets.baseline`; do not
print candidate secret values in CI logs.

When the scan fails:

1. Remove and rotate real secrets before updating the baseline.
2. For false positives, regenerate and audit the baseline locally:

```bash
python -m pip install detect-secrets==1.5.0
detect-secrets scan > .secrets.baseline
detect-secrets audit .secrets.baseline
git ls-files -z | xargs -0 detect-secrets-hook --baseline .secrets.baseline --no-verify
```

Commit `.secrets.baseline` only after the findings have been reviewed.

## Pinned GitHub Actions

Workflow `uses:` references are pinned to commit SHA with the source major tag
kept in a trailing comment, for example:

```yaml
uses: actions/checkout@11d5960a326750d5838078e36cf38b85af677262 # v4
```

To update a pinned action:

1. Resolve the intended tag to a commit SHA:

```bash
git ls-remote https://github.com/actions/checkout refs/tags/v4
```

2. Replace only the SHA, keep the comment matching the reviewed tag.
3. Review the upstream release notes before merging the update.
4. Run `git diff --check` and let CI verify the workflow.
