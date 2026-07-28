# Security Isolation Audit

Historical tenant-isolation audit and closure status. For the current security
posture and production operator checklist, see
[security-posture.md](security-posture.md).

## Scope

- RLS migrations for trace storage.
- Database session project context setup.
- Runtime database user and table ownership.
- Trace and metrics project-scoping assumptions.

## Historical Findings

- RLS is enabled on `spans` and `traces` by
  `backend/alembic/versions/bf79868b5f76_add_rls_policies.py`.
- Both policies compare `project_id` with
  `NULLIF(current_setting('app.current_project_id', true), '')::uuid`.
- `app.core.db.get_db(project_id=...)` sets `app.current_project_id` with
  `set_config(..., true)` when a project context is provided.
- The original local Docker-backed verification used one `llmobs`
  owner/runtime role. That role was a PostgreSQL superuser with `BYPASSRLS`, so
  it could see `spans` and `traces` rows without `app.current_project_id` even
  when RLS policies existed.
- The original verification also showed `relrowsecurity = true` and
  `relforcerowsecurity = false` for `spans` and `traces`.
- At that point, trace and metrics APIs still applied explicit `project_id`
  filters in service SQL, so application-level scoping existed, but database
  RLS was not yet an effective defense-in-depth boundary for the runtime role.
- At that point, JWT project selection validated active organization projects,
  but project membership enforcement was incomplete for ordinary users.

## Closure Status

The historical findings above are closed for the current production/runtime
role model:

- `backend/alembic/versions/3b9f1a2c4d6e_force_rls_on_trace_tables.py` applies
  `FORCE ROW LEVEL SECURITY` to `spans`, `traces` and their existing child
  partitions.
- Future monthly trace/span partitions created by
  `backend/app/workers/maintenance.py` enable and force RLS immediately after
  partition creation.
- `DATABASE_URL` is the runtime application role. In production,
  `backend/app/core/config.py` rejects `DATABASE_URL` values that use
  `POSTGRES_USER` or `postgres`.
- `MIGRATION_DATABASE_URL` is the Alembic owner/admin role used by
  `backend/alembic/env.py`.
- `backend/alembic/versions/d4e5f6a7b8c9_runtime_database_role_grants.py`
  creates or updates `POSTGRES_APP_USER` with
  `NOSUPERUSER NOBYPASSRLS` when `POSTGRES_APP_USER` and
  `POSTGRES_APP_PASSWORD` are available, then grants schema, table and sequence
  privileges for runtime access.
- `backend/tests/integration/test_runtime_role_rls.py` is the opt-in CI gate
  for physical isolation. It proves the runtime role is not superuser, does
  not have `BYPASSRLS`, sees no trace/span rows without
  `app.current_project_id`, sees only the selected project after setting the
  context, and verifies parent plus child trace/span partitions keep
  `ENABLE/FORCE ROW LEVEL SECURITY`.
- Project access now uses explicit project memberships for non-admin users via
  `backend/app/core/auth.py::get_project_for_user`; organization admins retain
  implicit access to organization projects.

## Current Guarantees

- Trace and span RLS is a defense-in-depth boundary for the dedicated runtime
  application role.
- Application APIs still enforce project scope explicitly before querying
  project data.
- Project API keys are project-scoped, hashed at rest and checked for
  operation scope.
- Ordinary organization users need explicit project membership for dashboard
  project data. Organization admins can manage and view organization projects.
- Global pricing writes require `users.is_platform_admin`; organization admin
  alone is not enough.

## Known Limitations

- RLS does not protect data from PostgreSQL superusers, `BYPASSRLS` roles or
  table owners. Production must keep `DATABASE_URL` on the non-owner runtime
  role and reserve `MIGRATION_DATABASE_URL` for migrations and maintenance.
- Existing PostgreSQL volumes do not rerun Docker init scripts automatically.
  Operators must run migrations with `POSTGRES_APP_USER` and
  `POSTGRES_APP_PASSWORD` available, then verify the app role before accepting
  tenant traffic.
- Pricing is still a global platform-default catalog. Organization-scoped
  pricing overrides are planned in [ADR 0001](adr/0001-pricing-tenancy.md).
- Dashboard login JWTs are intentionally bearer tokens stored in
  `localStorage` for this release. The accepted risk and mitigations are in
  [browser-token-storage.md](browser-token-storage.md).

## Original Verification Evidence

The Docker-backed SQL check returned:

- current user: `llmobs`;
- `spans` owner: `llmobs`, `relrowsecurity = true`,
  `relforcerowsecurity = false`;
- `traces` owner: `llmobs`, `relrowsecurity = true`,
  `relforcerowsecurity = false`;
- rows were visible from both tables while `app.current_project_id` was unset.
