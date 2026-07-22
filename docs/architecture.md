# Architecture

LLM Obs is a self-hosted observability stack for LLM calls. The runtime is split
between an ingest path optimized for accepting spans quickly and a query path
used by the dashboard and APIs.

![Dashboard](assets/dashboard.png)

## Components

```
Python SDK / OTLP clients
    |
    | HTTP batch with project API key
    v
FastAPI ingest API
    |
    | durable Redis queue
    v
Taskiq worker
    |-- PostgreSQL: traces, spans, outbox, aggregates, pricing, alerts, users
    |-- MinIO/S3: stored payload objects
    |-- Redis: cache, rate-limit counters, batch status and pub/sub
    |-- Redis queue: Taskiq queues, task results and DLQ
    `-- Mailpit/SMTP or Slack webhook: alert delivery

React dashboard
    |
    | REST API with JWT session
    v
FastAPI query/admin API
```

Production Compose adds PgBouncer between the backend services and PostgreSQL.
The scheduler runs maintenance jobs such as retention cleanup and partition
management. Partition maintenance uses the owner/admin migration connection to
create future monthly trace/span partitions ahead of time and warns if rows are
accumulating in default partitions. Retention cleanup is project-scoped and
batched: it deletes payload objects under the project's `payloads/{project_id}/`
prefix before removing old span rows, then removes trace rows that no longer
have spans.

## Ingest Flow

1. The Python SDK records spans with decorators or provider patching.
2. The SDK sends JSON span batches to `POST /v1/ingest` with a project API key.
3. OTLP HTTP trace export accepts native payloads at `POST /v1/traces`.
   Both binary protobuf (`application/x-protobuf`) and OTLP/JSON
   (`application/json`) trace exports are accepted. OTLP/JSON uses standard
   lowerCamelCase protobuf JSON field names such as `resourceSpans`,
   `scopeSpans`, `traceId`, `spanId`, `parentSpanId`,
   `startTimeUnixNano` and `endTimeUnixNano`.
   OTLP span attributes preserve primitive, array and key-value AnyValue
   shapes for processing. Recognized GenAI semantic conventions are promoted
   into first-class span fields: `gen_ai.provider.name`,
   `gen_ai.request.model` or `gen_ai.response.model`,
   `gen_ai.usage.input_tokens` and `gen_ai.usage.output_tokens`; unknown
   conventions fall back to `custom`, `unknown` and zero token counts.
4. The API authenticates the key, rate-limits the project and enqueues the batch.
5. OTLP ingest accepts native 16/32 character hex span and trace IDs by mapping
   them deterministically to internal UUIDs, while malformed spans are reported
   through OTLP `partialSuccess.rejectedSpans`. A fully malformed OTLP payload
   is rejected with HTTP 400 instead of being acknowledged as accepted.
   OTLP span `status.code=ERROR` maps to the internal span `error` field, so
   worker persistence and error-rate metrics treat the span as failed.
6. Workers process spans asynchronously, write spans and trace rows in one DB
   transaction, and create outbox events for live span delivery.
7. Workers update trace aggregates and evaluate alert rules after the span
   transaction commits.
8. Payloads are stored in MinIO/S3 only when project payload settings allow it.
9. The dashboard reads metrics, traces and analytics from the query API.

Accepted ingest requests return a `batch_id`. Processing can still fail later,
so operational checks should include the batch status API, failed-task API and
Prometheus metrics. Current end-to-end delivery semantics are documented in
[delivery-guarantees.md](delivery-guarantees.md).

## Storage Boundaries

PostgreSQL stores organizations, users, projects, API key hashes, pricing,
traces, spans, outbox events, alert rules, alert events, audit events and
failed-task metadata.
Runtime services should connect with the dedicated application database role,
while Alembic migrations use the owner/admin migration role. This keeps trace
RLS as a database-level defense-in-depth boundary instead of relying on a
superuser or table-owner runtime connection.

Governance mutations for users, projects and API keys write audit events in the
same database transaction as the audited change. If the audit insert fails, the
mutation fails and rolls back instead of silently committing an unaudited admin
change. Legacy `log_audit` calls without an active transaction remain
best-effort and suppress audit storage failures.

MinIO/S3 stores LLM input/output payload objects when enabled. Project settings
control payload mode, maximum payload size and comma-separated field names to
redact before object storage. PostgreSQL span rows store only payload object
keys plus non-sensitive storage status metadata such as omitted, oversized or
storage-failed. Span metadata stored in PostgreSQL is limited to an allowlist
of low-risk technical fields; prompts, provider system instructions,
authorization-like fields and arbitrary unknown metadata are not stored as
ordinary span metadata.

Redis storage is split by durability requirement. `REDIS_URL` is the cache and
coordination Redis for rate limits, short-lived caches, batch status and the
live span stream. `REDIS_QUEUE_URL` is the durable Taskiq queue/result Redis for
accepted ingest work, scheduled jobs and the DLQ; Compose configures it with AOF
persistence and `noeviction`.

Span live-stream delivery uses PostgreSQL transactional outbox rows. The worker
writes `span.inserted` outbox events in the same transaction as span/trace
storage; `deliver_span_outbox_events` publishes them to Redis and retries
pending events on a schedule. Trace aggregate and alert evaluation enqueueing
are still post-commit side effects and can lag or fail independently of raw span
storage.

## Authentication And Roles

Dashboard users authenticate with JWT sessions. Admin-only pages include
Pricing, Users, Audit Log and Project Settings. Users can be invited with a
24-hour token and set their own password when accepting the invite.

Pricing is currently stored in a global catalog even though the dashboard
exposes it to organization admins. The accepted target model is a hybrid
platform-default plus organization-override catalog with a separate
`platform_admin` boundary; see [ADR 0001](adr/0001-pricing-tenancy.md).

The browser dashboard stores the login JWT in `localStorage` for the next
release and sends it as `Authorization: Bearer ...`; the accepted risk,
mitigations and cookie migration boundary are documented in
`docs/browser-token-storage.md`.

Project API keys are separate from login tokens. They are hashed at rest,
displayed once, scoped to ingest/read/read-write operations and can be revoked
from Project Settings.

## Dashboard API Surface

The dashboard currently uses typed frontend helpers for:

- auth and invite acceptance
- overview metrics, timeseries and analytics
- trace list/detail with optional payload loading
- alert rules and events
- pricing records
- organization users and role changes
- project settings, legacy key rotation and managed API keys
- audit events

## Operations

Use `/health` for backend liveness and `/ready` for dependency readiness.
Prometheus metrics are exposed at `/metrics`. Worker and scheduler liveness is
reported by `/worker-health`, which reads the Redis timestamp written by the
scheduled worker heartbeat task. Runbooks for local development, production
Compose, migrations, rollback and smoke checks are in [runbooks.md](runbooks.md).
