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

## Backend critical regression policy

The backend CI `test` job keeps the aggregate coverage gate at
`--cov-fail-under=40`, but critical security and data-integrity behavior is
guarded by an explicit fail-fast test set:

```bash
python scripts/backend_critical_tests.py
```

This gate is required for backend changes that touch tenant isolation, ingest
delivery, retention, authentication, API keys, payload privacy, storage policy
or pricing/cost behavior. It intentionally lists test files instead of relying
only on the aggregate coverage percentage, because a high percentage can still
miss a broken critical invariant.

Current critical areas:

- Isolation and authorization:
  `tests/unit/test_config.py`,
  `tests/integration/test_auth_current_user.py`,
  `tests/integration/test_project_access_enforcement.py` and
  `tests/integration/test_api_key_policies.py`.
- Ingest and request safety:
  `tests/integration/test_ingest_batch_status.py` and
  `tests/unit/test_payload_size_limit.py`.
- Retention and payload privacy:
  `tests/integration/test_retention.py`,
  `tests/integration/test_payload_privacy.py` and
  `tests/unit/test_storage.py`.
- Authentication/bootstrap:
  `tests/integration/test_auth_api.py`.
- Pricing:
  `tests/integration/test_cost_service.py` and
  `tests/integration/test_pricing_api.py`.

If a security or data change adds a new invariant, update
`scripts/backend_critical_tests.py` in the same PR so CI exercises the new
regression boundary directly.

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

## Dependency vulnerability scanning

The `security` workflow job also runs dependency vulnerability gates for Python
runtime dependencies and frontend production dependencies.

Python packages are resolved from the backend and SDK project metadata, then
audited with `pip-audit` through a repository wrapper:

```bash
python -m pip install "pip-audit>=2.7,<3"
python scripts/pip_audit_gate.py --project backend --project sdk --allowlist security/pip-audit-allowlist.json
```

CI fails on any known vulnerability reported by `pip-audit` unless it is listed
in `security/pip-audit-allowlist.json`. Each allowlist entry must include the
package, advisory IDs, reason and expiry date. Prefer upgrading or constraining
the dependency instead of ignoring the advisory; keep allowlist entries
temporary and remove them when the dependency graph is fixed.

Frontend production dependencies are audited from `frontend/package-lock.json`
with a high-severity gate:

```bash
python scripts/npm_audit_gate.py --package-dir frontend --allowlist security/npm-audit-allowlist.json --audit-level high --omit dev
```

The wrapper runs `npm audit --json --omit=dev`, fails on unallowlisted
`high`/`critical` vulnerabilities, and keeps false positives in
`security/npm-audit-allowlist.json`. Each allowlist entry must include a
package and reason; optional advisory IDs narrow the ignore to a specific
finding. Keep entries temporary and remove them when the dependency graph is
fixed.

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
