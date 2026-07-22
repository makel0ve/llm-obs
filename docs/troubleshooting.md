# Troubleshooting

Use this checklist when the stack starts but data or admin pages do not behave
as expected.

## No Spans In Dashboard

1. Confirm the SDK process has `LLM_OBS_API_KEY` and `LLM_OBS_ENDPOINT`.
2. Use a project API key, not a dashboard JWT token.
3. From the host, use `http://localhost:8000`. From another Compose service,
   use `http://backend:8000`.
4. In scripts and CLIs, call `await llm_obs.shutdown()` before exit.
5. Select `1h` or `24h` in Overview/Traces if the trace is recent.
6. Check worker logs:

```bash
docker compose -f infra/docker-compose.yml logs --tail=100 worker
```

7. Check the worker heartbeat:

```bash
curl -f http://localhost:8000/worker-health
docker compose -f infra/docker-compose.yml logs --tail=100 scheduler
```

`/worker-health` returns `503` with `missing` until the scheduler has enqueued
and the worker has executed the first heartbeat task. A `stale` response means
that path has stopped updating Redis within the configured threshold.

## Ingest Accepted But Trace Missing

Check batch processing:

```bash
curl -H "X-API-Key: $LLM_OBS_API_KEY" \
  http://localhost:8000/v1/ingest/batches/YOUR_BATCH_ID
```

Check failed-task summaries with an admin JWT:

```bash
curl -H "Authorization: Bearer YOUR_JWT_TOKEN" \
  "http://localhost:8000/v1/failed-tasks?project_id=YOUR_PROJECT_ID"
```

Admins can also inspect recent failed ingestion tasks in Project Settings. The
diagnostics table shows task name, safe argument summaries, error text, attempts
and resolution state. It does not show full prompts, model outputs or secret
values.

Retry is available only when the failed-task record still contains a complete
safe payload for the background task. Summary-only records, including records
that only show `batch_id`, `project_id` and `span_count`, cannot be retried
because the original spans are not stored there.

If batch status is `processed` but live dashboard updates lag, check for
`PENDING` or `FAILED` `span.inserted` rows in `outbox_events` and verify Redis
health. Span storage can be committed before live Pub/Sub delivery completes.
The current delivery boundaries are detailed in
[delivery-guarantees.md](delivery-guarantees.md).

## Auth Or Redirect Loop

- Clear stale local storage or log out and log in again.
- Verify the backend uses the same `SECRET_KEY` across restarts in production.
- Check that `VITE_API_URL` points to the backend URL reachable by the browser.
- Confirm migrations were applied after pulling new code.

## Admin Page Cannot Load Data

Most admin pages require the `admin` role. If Users, Pricing, Audit Log or
Project Settings return errors, verify:

```bash
docker compose -f infra/docker-compose.yml exec backend alembic upgrade head
docker compose -f infra/docker-compose.yml logs --tail=100 backend
```

Use `/ready` to check dependencies:

```bash
curl http://localhost:8000/ready
```

`/ready` treats PostgreSQL and Redis as critical. S3/MinIO payload storage is
reported as `ok`, `missing` or `degraded`; a degraded S3 check does not block
metadata ingest, but new payload writes record `payload_status=storage_failed`.

## API Key Problems

- Legacy project keys and managed API keys are shown only once.
- If a key is lost, create or rotate a key in Project Settings.
- If a key is exposed, revoke it or rotate the legacy project key immediately.
- Use an ingest or read-write key for SDK ingestion.

## Payloads Not Visible In Trace Detail

Trace detail does not load payload objects until `Load payload` is used.
Payloads may still be absent when:

- project payload storage mode is `Do not store payloads`
- mode is `Store only error payloads` and the span succeeded
- the payload exceeded `Max payload bytes`
- object storage failed before a payload key was recorded
- the span was created by an older version that omitted small payloads before
  object storage

New spans include span-level `payload_status` and `payload_drop_reason` fields
in Trace Detail. Older spans may show an unknown payload status because they
were created before these fields existed.

## Pricing Or Costs Look Wrong

- Add a Pricing record for the exact provider and model names used by spans.
- Historical pricing uses validity intervals; expired records are kept for old
  traces.
- If a price was edited, refresh the dashboard and confirm the active interval.

## Alerts Do Not Fire

- Confirm the rule is active and belongs to the current project.
- Check the metric, threshold, window and cooldown.
- For latency, error-rate and cost alerts, verify the scheduler is running and
  `/worker-health` reports a fresh scheduled heartbeat; these windowed rules no
  longer run after every ingest batch.
- For anomaly alerts, verify the worker is processing ingest batches for the
  project.
- For email, verify SMTP settings and Mailpit or provider logs.
- For Slack, verify the webhook URL and network access from the backend. Alert
  webhook delivery allows only `hooks.slack.com` and `hooks.slack-gov.com`
  HTTPS URLs on the default port, resolves DNS before delivery, blocks
  private/link-local/loopback/internal addresses and validates redirect targets
  before sending another request.

## Useful Commands

```bash
docker compose -f infra/docker-compose.yml ps
docker compose -f infra/docker-compose.yml logs --tail=100 backend
docker compose -f infra/docker-compose.yml logs --tail=100 worker
curl http://localhost:8000/ready
curl http://localhost:8000/metrics | grep -E 'llmobs_ingest|llmobs_payload_storage'
curl http://localhost:8000/metrics | grep llmobs_taskiq_queue
```
