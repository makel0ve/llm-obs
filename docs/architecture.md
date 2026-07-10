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
    | Redis queue
    v
Taskiq worker
    |-- PostgreSQL: traces, spans, aggregates, pricing, alerts, users
    |-- MinIO/S3: large stored payload objects
    |-- Redis: cache, queue and pub/sub
    `-- Mailpit/SMTP or Slack webhook: alert delivery

React dashboard
    |
    | REST API with JWT session
    v
FastAPI query/admin API
```

Production Compose adds PgBouncer between the backend services and PostgreSQL.
The scheduler runs maintenance jobs such as retention cleanup and partition
management.

## Ingest Flow

1. The Python SDK records spans with decorators or provider patching.
2. The SDK sends batches to `POST /v1/spans` with a project API key.
3. The API authenticates the key, rate-limits the project and enqueues the batch.
4. Workers process spans asynchronously, update trace aggregates and evaluate
   alert rules.
5. Large payloads are stored in MinIO/S3 only when project payload settings
   allow it.
6. The dashboard reads metrics, traces and analytics from the query API.

Accepted ingest requests return a `batch_id`. Processing can still fail later,
so operational checks should include the batch status API, failed-task API and
Prometheus metrics.

## Storage Boundaries

PostgreSQL stores organizations, users, projects, API key hashes, pricing,
traces, spans, alert rules, alert events, audit events and failed-task metadata.

MinIO/S3 stores large LLM input/output payload objects when enabled. Project
settings control payload mode, maximum payload size and comma-separated field
names to redact before object storage.

Redis stores queue data, caches, rate-limit counters and the live span stream.

## Authentication And Roles

Dashboard users authenticate with JWT sessions. Admin-only pages include
Pricing, Users, Audit Log and Project Settings. Users can be invited with a
24-hour token and set their own password when accepting the invite.

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

Use `/health` for liveness and `/ready` for dependency readiness. Prometheus
metrics are exposed at `/metrics`. Runbooks for local development, production
Compose, migrations, rollback and smoke checks are in [runbooks.md](runbooks.md).
