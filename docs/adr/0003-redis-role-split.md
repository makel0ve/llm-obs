# ADR 0003 - Redis Role Split

Date: 2026-07-28

## Status

Accepted.

## Context

LLM Obs uses Redis for both low-durability coordination and durable work
queueing. Combining these responsibilities in one eviction-capable Redis risks
losing accepted ingest work or DLQ/task result state under cache pressure.

## Decision

Split Redis by durability requirement:

- `REDIS_URL` is cache and coordination Redis. It holds rate-limit counters,
  short-lived caches, batch status and live Pub/Sub state.
- `REDIS_QUEUE_URL` is durable Taskiq queue/result Redis. It holds accepted
  ingest work, scheduled jobs, task results and DLQ-related state.

Production Compose should configure the queue Redis with persistent storage and
`noeviction`. If `REDIS_QUEUE_URL` is omitted, the application falls back to
`REDIS_URL`; that fallback is acceptable for local development, not for
production guarantees.

## Consequences

Readiness reports `redis_cache` and `redis_queue` separately. Both are critical
for the backend readiness contract, while S3 payload storage remains
non-critical because metadata ingest can degrade to `payload_status=storage_failed`.

Operators should size and alert on cache Redis and queue Redis independently.
Queue depth and oldest-job-age metrics apply to the durable Taskiq queue.

The application must avoid placing durable accepted work exclusively in
eviction-prone Redis structures.

## Open Decisions

- Whether batch status should eventually move from cache Redis to PostgreSQL for
  stronger long-term recovery.
- Whether Redis queue persistence settings should become an automated startup
  validation instead of a documented Compose/runtime requirement.
