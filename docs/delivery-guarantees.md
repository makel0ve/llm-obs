# Telemetry Delivery Guarantees

This document describes the current telemetry delivery behavior. It is an
operator contract, not a promise of stronger semantics than the implementation
provides.

## End-To-End Path

1. The SDK records spans in memory and sends JSON batches to `POST /v1/ingest`
   with a project API key.
2. The ingest API authenticates the key, applies project rate limits and, when
   provided, reserves the request `idempotency_key` in PostgreSQL.
3. The API writes an accepted batch status in Redis and enqueues
   `process_span_batch` on the durable Taskiq Redis queue.
4. The worker marks the batch `processing`, prepares span rows, stores allowed
   selected payloads in object storage and writes spans, trace rows and span
   Pub/Sub outbox events in one PostgreSQL transaction.
5. After commit, the worker increments ingest metrics, enqueues span outbox
   delivery, enqueues trace aggregate updates and evaluates alert rules.
6. The span outbox consumer publishes `span.inserted` events to the live Redis
   stream and marks outbox rows delivered. Retryable failures stay in
   `outbox_events` for scheduled retry.
7. Query APIs read traces, spans, metrics and analytics from PostgreSQL for the
   dashboard.

OTLP HTTP ingest at `POST /v1/traces` accepts native OTLP trace/span IDs and
maps them into the same storage model. Its malformed-span behavior is reported
through OTLP `partialSuccess.rejectedSpans` when at least one span is accepted.
Fully malformed OTLP payloads that cannot be decoded are rejected with HTTP 400
and are not enqueued. OTLP span `status.code=ERROR` is converted into the
internal span `error` field, so persisted span status and error-rate metrics
reflect the source telemetry error.

## Guarantees By Segment

| Segment | Current guarantee | Notes |
| --- | --- | --- |
| SDK buffer to HTTP request | At-most-once unless the caller flushes and retries | Short-lived scripts must call `await llm_obs.shutdown()` before exit. Process termination before flush can drop buffered spans. |
| HTTP ingest acceptance | At-least-once enqueue after accepted response | The API returns `202` after writing accepted batch status and enqueueing worker work. If enqueue fails, the request fails and the batch is marked failed. |
| Client timeout around ingest | Unknown from the client without lookup | If the client times out, check the returned `batch_id` when available or retry with the same `idempotency_key`. |
| Idempotency key reservation | Effectively-once per project/key/request body for accepted batch result | Identical committed requests return the original `batch_id`; in-flight duplicates return `409`; same key with a different body returns `409`; failed enqueue attempts can be retried. |
| Taskiq queue to worker execution | At-least-once | Worker tasks can retry. The worker must tolerate duplicate batches and duplicate span IDs. |
| Span and trace database write | Effectively-once per span id/start time | Span insert uses conflict handling. Duplicate span rows are ignored and `processed` counts only rows actually inserted. Trace identity is stabilized by earliest known start time. |
| Worker validation failures for individual spans | Partial success | Permanent per-span processing errors are counted as dropped spans and produce `partial_failed` batch status when other spans succeed. |
| Transient worker failures before DB commit | At-least-once retry | Transient DB, Redis, storage/client and timeout errors are raised for Taskiq retry and the batch status is marked failed for visibility until a retry succeeds. |
| Span live Pub/Sub delivery | At-least-once through outbox retry | `span.inserted` outbox rows are committed with span state, then delivered to Redis by `deliver_span_outbox_events`. Consumers should treat live stream messages as duplicate-tolerant hints. |
| Trace aggregate enqueue after commit | Best-effort post-commit side effect | Aggregate update tasks are still enqueued after the span transaction. A failure here can mark the batch failed even though span rows are committed; rerunning aggregate work can repair derived trace totals. |
| Alert evaluation after commit | Best-effort post-commit side effect | Alert evaluation runs after span commit and can fail independently of persisted telemetry. Alert delivery has its own cooldown and notification safeguards. |
| Query API reads | Read-after-commit for stored rows; derived values may lag | Raw spans are queryable after commit. Trace totals, ended-at and live dashboard streams can lag until aggregate and outbox workers run. |

## Failure Scenarios

Client timeout before a response does not prove that ingest failed. The Python
SDK automatically sends one `idempotency_key` per flush batch and reuses it for
retries of that same batch. Raw ingest clients should retry with the same
`idempotency_key` when they supplied one. If the original request committed, the
retry returns the original `batch_id`. If the original request is still pending,
the retry returns `409` for in-progress processing.

Duplicate requests without an `idempotency_key` can enqueue duplicate worker
tasks. Duplicate span IDs are not inserted twice, but the batch ids and status
records are separate.

Worker retry can reprocess the same batch. Span rows use conflict handling, so
already stored spans are skipped and batch `processed` counts only newly
inserted rows. This protects storage from duplicate rows, but post-commit
aggregate and alert side effects can still need operator inspection when worker
failures repeat.

Outbox backlog affects live Redis stream freshness, not committed telemetry
storage. Raw spans can be visible in query APIs before live Pub/Sub delivery is
complete. Inspect `outbox_events` when live updates lag but batch status and
trace queries show stored spans.

## Operator Checklist

Use this checklist when validating delivery after deploys or incidents:

- Send a known span through the SDK and call `await llm_obs.shutdown()` before
  the test process exits.
- Confirm `POST /v1/ingest` returns `202` with a `batch_id`.
- Poll `GET /v1/ingest/batches/{batch_id}` until status is `processed`,
  `partial_failed` or `failed`.
- Retry the same request with the same `idempotency_key` and verify the same
  `batch_id` is returned.
- Verify `/worker-health` is fresh and worker logs do not show repeated
  `process_span_batch` failures.
- Check `/metrics` for `llmobs_ingest_batches_processed_total`,
  `llmobs_ingest_batches_failed_total` and `llmobs_spans_ingested_total`.
- If live dashboard updates lag, inspect `outbox_events` for `PENDING` or
  `FAILED` `span.inserted` rows and check Redis health.
- If traces are stored but totals look stale, rerun or inspect trace aggregate
  work before treating raw telemetry as lost.
