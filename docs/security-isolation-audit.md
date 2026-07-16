# Security Isolation Audit

Block 01 audit result for the next hardening release.

## Scope

- RLS migrations for trace storage.
- Database session project context setup.
- Runtime database user and table ownership.
- Trace and metrics project-scoping assumptions.

## Findings

- RLS is enabled on `spans` and `traces` by
  `backend/alembic/versions/bf79868b5f76_add_rls_policies.py`.
- Both policies compare `project_id` with
  `current_setting('app.current_project_id', true)::uuid`.
- `app.core.db.get_db(project_id=...)` sets `app.current_project_id` with
  `set_config(..., true)` when a project context is provided.
- Local Docker-backed verification showed the runtime/migration database role is
  `llmobs`, and both `spans` and `traces` are owned by `llmobs`.
- Follow-up verification during Block 02 showed the local `llmobs` role is a
  PostgreSQL superuser with `BYPASSRLS`; such roles bypass RLS even when
  `FORCE ROW LEVEL SECURITY` is enabled.
- Local Docker-backed verification showed `relrowsecurity = true` and
  `relforcerowsecurity = false` for both tables.
- Local Docker-backed verification showed the `llmobs` owner role can see rows
  from `spans` and `traces` without `app.current_project_id` being set. Current
  RLS is therefore not an effective runtime isolation boundary for the owner
  role.
- Trace and metrics APIs still apply explicit `project_id` filters in service
  SQL and use `get_db(project_id=...)`, so API behavior is protected by
  application-level scoping even though owner-bypass weakens database
  defense-in-depth.
- JWT project selection currently validates that the requested project is active
  and belongs to the user's organization. Project membership enforcement does
  not exist yet, so ordinary organization users can access any active
  organization project if they know its `project_id`.

## Recommendation

- In Block 02, apply `FORCE ROW LEVEL SECURITY` to `spans`, `traces` and their
  existing partitions as the smallest safe hardening step.
- Ensure future trace/span partitions are created with RLS enabled and forced.
- Use a runtime application role without `SUPERUSER` and without `BYPASSRLS`.
  `FORCE ROW LEVEL SECURITY` does not protect rows from those privileged roles.
- Keep separate migration-owner and runtime-application roles as the production
  deployment direction when stronger role separation is needed.

## Block 33 Closure

Block 33 converts the runtime-role recommendation into the Docker and settings
contract:

- `DATABASE_URL` is the runtime application role and is rejected in production if
  it uses `POSTGRES_USER` or `postgres`.
- `MIGRATION_DATABASE_URL` is the Alembic owner/admin role and is used by
  `backend/alembic/env.py`.
- Docker Compose defines `POSTGRES_APP_USER` and `POSTGRES_APP_PASSWORD`; new
  Postgres volumes create the app role with `NOSUPERUSER NOBYPASSRLS`.
- The Block 33 migration grants current and future `public` schema table and
  sequence privileges to `POSTGRES_APP_USER` when that environment variable is
  available.

## Verification Evidence

The Docker-backed SQL check returned:

- current user: `llmobs`;
- `spans` owner: `llmobs`, `relrowsecurity = true`,
  `relforcerowsecurity = false`;
- `traces` owner: `llmobs`, `relrowsecurity = true`,
  `relforcerowsecurity = false`;
- rows were visible from both tables while `app.current_project_id` was unset.
