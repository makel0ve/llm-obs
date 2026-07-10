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

- In Block 02, apply `FORCE ROW LEVEL SECURITY` to `spans` and `traces` as the
  smallest safe hardening step.
- Verify that the owner role no longer sees trace/span rows without
  `app.current_project_id`.
- Keep separate migration-owner and runtime-application roles as a follow-up
  option if production deployments need stronger role separation.

## Verification Evidence

The Docker-backed SQL check returned:

- current user: `llmobs`;
- `spans` owner: `llmobs`, `relrowsecurity = true`,
  `relforcerowsecurity = false`;
- `traces` owner: `llmobs`, `relrowsecurity = true`,
  `relforcerowsecurity = false`;
- rows were visible from both tables while `app.current_project_id` was unset.
