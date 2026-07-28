# Security Posture

This document describes the current security posture for production-like
self-hosted deployments. Historical findings and closure notes live in
[security-isolation-audit.md](security-isolation-audit.md).

## Current Guarantees

- Authentication uses signed JWT login sessions for dashboard users and
  separate project API keys for SDK/ingest/query access.
- Backend auth reloads the current user row on each JWT request, so disabled,
  deleted or demoted users do not keep stale database-backed privileges until
  token expiry.
- Project API keys are hashed at rest, displayed once, scoped to
  `ingest`, `read` or `read_write`, and can be revoked from Project Settings.
- Public registration can be disabled with `PUBLIC_REGISTRATION_ENABLED=false`;
  first-admin bootstrap then requires `BOOTSTRAP_ADMIN_TOKEN` before any user
  exists, and registration stays closed after bootstrap.
- Organization admins can manage organization users and projects. Non-admin
  users need explicit project membership for dashboard project data.
- Global pricing writes require the separate `users.is_platform_admin`
  capability.
- Trace and span rows have row-level security policies keyed by
  `app.current_project_id`. Parent and child trace/span partitions are expected
  to keep `ENABLE/FORCE ROW LEVEL SECURITY`.
- The CI runtime-role RLS gate verifies that the runtime app role is not a
  superuser, does not have `BYPASSRLS`, cannot read trace/span rows without
  project context, and sees only the selected project after context is set.
- Payload storage is explicit and project-configured. Prompt/output payloads
  are redacted before S3/MinIO writes; PostgreSQL stores payload object keys
  and storage status, not raw prompt/output content.
- Span metadata persisted in PostgreSQL is limited to a low-risk allowlist;
  prompt, system, authorization-like and arbitrary unknown metadata are
  dropped before persistence.
- Slack webhook targets are limited to official Slack incoming-webhook domains.
  Webhook delivery validates DNS results, blocks private/internal addresses and
  validates redirect targets.
- Production frontend responses include CSP and browser security headers.
  Backend API responses include non-CSP security headers suitable for JSON API
  clients.
- CI scans tracked files with `detect-secrets`, runs Python and frontend
  dependency vulnerability gates, pins GitHub Actions by commit SHA, scans
  production Docker images with Trivy and uploads image SBOM artifacts.

## Accepted Risks And Limitations

- Dashboard login JWTs are stored in `localStorage` for this release. A
  successful XSS issue in the dashboard origin could exfiltrate the active JWT
  until it expires or `SECRET_KEY` is rotated. Mitigations and the future
  HttpOnly cookie boundary are documented in
  [browser-token-storage.md](browser-token-storage.md).
- RLS is not a substitute for correct database role separation. PostgreSQL
  superusers, `BYPASSRLS` roles and table owners can bypass row-level security.
- Existing production PostgreSQL volumes may predate the app runtime role. They
  need migration and role verification before accepting tenant traffic.
- Pricing records are currently global platform defaults. Organization-scoped
  pricing overrides are planned in [ADR 0001](adr/0001-pricing-tenancy.md).
- Helm manifests are experimental and less exercised than Docker Compose.
- Browser E2E and automated accessibility/contrast checks are not configured
  yet.

## Production Operator Controls

Before exposing a production deployment:

1. Set `ENVIRONMENT=production`.
2. Set a random 32+ character `SECRET_KEY`.
3. Set `PUBLIC_REGISTRATION_ENABLED=false` and a random
   `BOOTSTRAP_ADMIN_TOKEN` before first-admin registration.
4. Use HTTPS through a trusted reverse proxy and set `CORS_ALLOWED_ORIGINS` to
   exact dashboard origins, never `*`.
5. Keep PostgreSQL, Redis, Redis queue, MinIO/S3, PgBouncer and Mailpit/SMTP
   management ports off the public internet.
6. Use `DATABASE_URL` for the non-owner runtime app role and
   `MIGRATION_DATABASE_URL` for the owner/admin migration role.
7. Verify the runtime database role is `NOSUPERUSER NOBYPASSRLS`:

```bash
docker compose --env-file infra/.env -f infra/docker-compose.prod.yml exec postgres \
  psql -U "$POSTGRES_USER" -d "$POSTGRES_DB" \
  -c "SELECT rolname, rolsuper, rolbypassrls FROM pg_roles WHERE rolname IN ('$POSTGRES_USER', '$POSTGRES_APP_USER');"
```

8. Run the runtime-role RLS gate after migrations:

```bash
docker compose -f infra/docker-compose.yml exec backend \
  env RUN_RUNTIME_RLS_TESTS=1 pytest tests/integration/test_runtime_role_rls.py -q
```

9. Grant `users.is_platform_admin=true` only to users who should manage global
   platform defaults such as pricing.
10. Keep `detect-secrets`, dependency audits, image scanning and SBOM artifacts
    in the release workflow; review allowlist entries before expiry.
11. Rotate project API keys after exposure and rotate `SECRET_KEY` if login
    JWTs may have been exposed.

## Validation References

- Runtime role and RLS: [ci-security.md](ci-security.md#runtime-database-role-rls)
- Runtime role decision:
  [ADR 0004](adr/0004-runtime-role-rls-boundary.md)
- Payload policy decision:
  [ADR 0005](adr/0005-payload-storage-policy.md)
- Production runbook: [runbooks.md](runbooks.md)
- Browser token decision: [browser-token-storage.md](browser-token-storage.md)
- Architecture boundaries: [architecture.md](architecture.md)
- Critical regression policy:
  [audit-regression-coverage.md](audit-regression-coverage.md)
