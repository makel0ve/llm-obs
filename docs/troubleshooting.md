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

## API Key Problems

- Legacy project keys and managed API keys are shown only once.
- If a key is lost, create or rotate a key in Project Settings.
- If a key is exposed, revoke it or rotate the legacy project key immediately.
- Use an ingest or read-write key for SDK ingestion.

## Payloads Not Visible In Trace Detail

Trace detail does not load large payload objects until `Load payload` is used.
Payloads may still be absent when:

- project payload storage mode is `Do not store payloads`
- mode is `Store only error payloads` and the span succeeded
- the payload exceeded `Max payload bytes`
- the span only had inline metadata and no large stored payload object

## Pricing Or Costs Look Wrong

- Add a Pricing record for the exact provider and model names used by spans.
- Historical pricing uses validity intervals; expired records are kept for old
  traces.
- If a price was edited, refresh the dashboard and confirm the active interval.

## Alerts Do Not Fire

- Confirm the rule is active and belongs to the current project.
- Check the metric, threshold, window and cooldown.
- For email, verify SMTP settings and Mailpit or provider logs.
- For Slack, verify the webhook URL and network access from the backend.

## Useful Commands

```bash
docker compose -f infra/docker-compose.yml ps
docker compose -f infra/docker-compose.yml logs --tail=100 backend
docker compose -f infra/docker-compose.yml logs --tail=100 worker
curl http://localhost:8000/ready
curl http://localhost:8000/metrics | grep llmobs_ingest
```
