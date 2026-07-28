# ADR 0004 - Runtime Role RLS Boundary

Date: 2026-07-28

## Status

Accepted.

## Context

Trace and span data is project-scoped and must not leak across tenants. The
backend also applies explicit project filters, but the database should provide
defense in depth for the runtime application role.

PostgreSQL row-level security does not protect rows from superusers,
`BYPASSRLS` roles or table owners. Earlier local deployments used one database
owner/runtime role, which weakened RLS as a runtime isolation boundary.

## Decision

Use separate database roles:

- `MIGRATION_DATABASE_URL` is the owner/admin migration connection.
- `DATABASE_URL` is the non-owner runtime application connection.

The runtime role must be `NOSUPERUSER NOBYPASSRLS` and must not own trace/span
tables. Production configuration rejects a runtime `DATABASE_URL` that uses
`POSTGRES_USER` or `postgres`.

Trace and span parent tables and child partitions must keep
`ENABLE ROW LEVEL SECURITY` and `FORCE ROW LEVEL SECURITY`. RLS policies use
`NULLIF(current_setting('app.current_project_id', true), '')::uuid` so an unset
project context does not expose rows.

## Consequences

Migrations and partition maintenance require owner/admin credentials. Runtime
services must connect through the app role.

CI includes an opt-in runtime-role RLS gate that proves the runtime role sees no
trace/span rows without `app.current_project_id`, sees only the selected project
after context is set, and verifies parent plus child partitions keep RLS
enabled and forced.

Existing PostgreSQL volumes need explicit migration and role verification
because Docker init scripts do not rerun automatically.

## Open Decisions

- Whether additional project-scoped tables should receive PostgreSQL RLS beyond
  trace/span storage.
- Whether runtime-role RLS checks should become mandatory in every local
  developer test run or remain CI/production-smoke focused.
