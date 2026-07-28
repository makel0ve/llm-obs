# ADR 0002 - Telemetry Delivery Semantics

Date: 2026-07-28

## Status

Accepted.

## Context

LLM Obs accepts telemetry through the Python SDK ingest API and the OTLP HTTP
endpoint. The system has multiple boundaries with different failure modes:
client buffering, HTTP acceptance, idempotency reservation, Taskiq queueing,
worker database writes, object storage, transactional outbox delivery,
aggregate updates and scheduled alerts.

Treating the whole path as exactly-once would overstate the current
implementation and mislead operators during incident response.

## Decision

Document and implement delivery as segmented guarantees:

- SDK buffering is at-most-once unless the caller flushes and retries.
- HTTP ingest acceptance is at-least-once enqueue after a successful accepted
  response.
- Idempotency keys are project-scoped and effectively-once for the same request
  body and committed accepted batch result.
- Taskiq queue execution is at-least-once, so worker code must tolerate
  duplicate batches and duplicate span IDs.
- Span and trace database writes are effectively-once per span id/start time.
- Span live-stream delivery is at-least-once through PostgreSQL transactional
  outbox retry.
- Trace aggregate enqueueing, batch anomaly checks and scheduled alert delivery
  are best-effort side effects that can lag or fail independently of raw span
  storage.
- Query APIs are read-after-commit for stored rows, while derived trace totals
  and live stream freshness can lag.

The operator-facing contract remains in
[../delivery-guarantees.md](../delivery-guarantees.md), which is the source for
detailed failure scenarios and manual verification.

## Consequences

Operators must use batch status, failed-task records, outbox backlog metrics and
trace queries together before declaring telemetry lost.

Clients that retry after a timeout should reuse the same `idempotency_key` when
they supplied one. The Python SDK generates one key per flush batch and reuses
it for retries of that batch.

Consumers of live stream events must tolerate duplicates and treat live updates
as hints, not as the source of truth for persisted telemetry.

## Open Decisions

- Whether trace aggregate enqueueing should move fully behind a transactional
  outbox event.
- Whether batch-scoped anomaly checks should become an outbox or scheduled
  projection.
- Whether latency P95 alerting should use histogram/sketch buckets instead of
  exact raw-span percentile queries.
