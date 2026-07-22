# Platform SLOs

This document defines the initial self-hosted pilot SLOs for the LLM Obs
platform. These are operator targets for one deployment, not a hosted-service
contract. Use them to decide when to page, investigate or defer work during the
pilot.

The SLOs below only rely on signals that exist today. Where instrumentation is
not yet specific enough, the table marks the target as a watch metric instead
of a formal SLO.

## Scope

Covered:

- JSON ingest at `POST /v1/ingest`.
- OTLP ingest at `POST /v1/traces`.
- Async worker processing after a batch is accepted.
- Raw span persistence and bounded permanent span drops.
- Query API availability for dashboard reads.
- Live dashboard stream freshness through the span outbox backlog.

Not covered:

- Client-side SDK buffering before an HTTP request is sent.
- User-defined alert notification delivery latency.
- LLM provider availability, model latency or model accuracy.
- Payload object durability beyond the S3/MinIO service selected by the
  operator.

## SLO Table

| Area | SLI | Pilot SLO | Signals | Response |
| --- | --- | --- | --- | --- |
| Ingest API availability | Successful ingest API requests divided by total ingest API requests, excluding expected 4xx auth, validation and rate-limit responses. | 99.5% over 7 days. | FastAPI/Instrumentator HTTP request metrics for `POST /v1/ingest` and `POST /v1/traces`; `/ready`; `llmobs_ingest_batches_accepted_total`; `llmobs_ingest_batches_failed_total{stage="enqueue"}`. | Treat sustained 5xx or enqueue failures as an ingest incident. Check backend logs, Redis queue health, `/ready` and API key/rate-limit changes. |
| Worker pickup lag | P95 time from API batch acceptance to worker processing start. | P95 under 60 seconds over 1 hour. | `llmobs_ingest_batch_accepted_to_processing_seconds`; `llmobs_taskiq_queue_depth{queue="taskiq"}`; `llmobs_taskiq_queue_oldest_job_age_seconds{queue="taskiq"}`; `/worker-health`. | Scale workers or reduce expensive worker side effects. Check `redis-queue`, Taskiq worker logs and DLQ/failed-task records. |
| End-to-end ingest lag | P95 time from API batch acceptance to final worker batch status. | P95 under 5 minutes over 1 hour. | `llmobs_ingest_batch_accepted_to_finished_seconds`; `llmobs_ingest_batches_processed_total{status="processed|partial_failed"}`; `llmobs_ingest_batches_failed_total{stage="worker"}`. | Investigate DB latency, S3 latency, worker retries, queue depth and repeated transient failures. |
| Permanent span loss | Permanently dropped spans divided by accepted spans. | Under 0.1% over 7 days. | `llmobs_ingest_spans_dropped_total`; `llmobs_ingest_span_processing_failures_total{reason="..."}`; batch status `partial_failed`; OTLP `partialSuccess.rejectedSpans`. | Inspect top failure reasons. Invalid timestamps or missing fields usually indicate SDK/client payload bugs; broad `processing_error` growth needs backend investigation. |
| Payload storage reliability | Payload storage failures divided by payload storage attempts where payload storage is expected. | Watch metric only for this release. | `llmobs_payload_storage_results_total{status="storage_failed",reason="s3_error"}`; `llmobs_payload_storage_failures_total{stage="readiness|startup|store"}`; `/ready` S3 status. | If S3 is degraded, metadata ingest can still succeed. Investigate MinIO/S3 credentials, bucket existence and object storage latency before treating raw telemetry as lost. |
| Query API availability | Successful dashboard/query API reads divided by total dashboard/query API reads, excluding expected 4xx authorization and validation responses. | 99.5% over 7 days once route-labeled HTTP metrics are verified in the deployment. | FastAPI/Instrumentator HTTP request metrics for `/v1/metrics/*`, `/v1/traces*`, `/v1/alerts*`; `/ready`. | Treat sustained 5xx as a query-path incident. Check Postgres, PgBouncer, migrations, slow queries and partition pruning. |
| Live stream freshness | Pending or failed live-stream outbox rows. | Watch metric only for this release; page if backlog grows for more than 15 minutes while batch status is processed. | `llmobs_outbox_backlog{event_type="span.inserted",status="PENDING|FAILED"}`; `llmobs_outbox_delivery_attempts_total{event_type="span.inserted",result="failed"}`. | This affects dashboard live updates, not committed raw spans. Check Redis health and `deliver_span_outbox_events` worker logs. |

## Suggested Prometheus Alerts

Tune these expressions for the deployment's scrape interval and traffic volume.
They are starting points, not release defaults.

```promql
# Ingest accepted but workers are not keeping up.
histogram_quantile(
  0.95,
  sum(rate(llmobs_ingest_batch_accepted_to_processing_seconds_bucket[10m])) by (le)
) > 60

# End-to-end async ingest is slow.
histogram_quantile(
  0.95,
  sum(rate(llmobs_ingest_batch_accepted_to_finished_seconds_bucket[10m])) by (le)
) > 300

# Oldest queued job has exceeded the pickup SLO.
llmobs_taskiq_queue_oldest_job_age_seconds{queue="taskiq"} > 60

# Worker failures are happening.
increase(llmobs_ingest_batches_failed_total{stage="worker"}[15m]) > 0

# Permanent per-span drops are increasing.
increase(llmobs_ingest_spans_dropped_total[15m]) > 0

# Live stream outbox is stuck.
sum(llmobs_outbox_backlog{event_type="span.inserted",status=~"PENDING|FAILED"}) > 0
```

For API availability SLOs, use the HTTP request metrics exposed by
`prometheus-fastapi-instrumentator` in the running deployment. Verify the exact
metric names and route labels from `/metrics` before creating alerts, because
the exported series can vary by library version and configuration. Do not count
expected `401`, `403`, `404`, `409`, `413` or `429` responses as platform
availability failures.

## Operational Response

When an SLO burn or watch metric fires:

1. Classify the impact first: API acceptance failure, worker lag, permanent span
   drop, payload-only failure, query failure or live-stream delay.
2. Check `/ready` and `/worker-health`.
3. Check `llmobs_taskiq_queue_depth` and
   `llmobs_taskiq_queue_oldest_job_age_seconds` before scaling workers.
4. Check `llmobs_ingest_span_processing_failures_total` by reason before
   treating `partial_failed` as backend data loss.
5. Check `llmobs_payload_storage_results_total` before treating missing payload
   objects as missing span metadata.
6. Check `llmobs_outbox_backlog` before treating stale dashboard live updates as
   missing stored spans.
7. Use [delivery-guarantees.md](delivery-guarantees.md) to separate committed
   telemetry from post-commit side effects.

## Instrumentation Gaps

These are intentionally not formal SLOs yet:

- SDK buffer loss before an HTTP request reaches the backend. The backend cannot
  observe process termination before flush.
- Query availability by product surface until the deployment verifies stable
  route-labeled HTTP metrics.
- Payload durability beyond the configured object store's own guarantees.
- Alert notification latency and success rate by destination. Delivery hardening
  exists, but platform-wide notification SLOs need destination-specific metrics
  and operator policy.
