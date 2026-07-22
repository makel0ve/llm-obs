# Alert Evaluation Cost Audit

Date: 2026-07-22

Scope: Big Block 08.1, current alert evaluation hot path and recommended
scheduled evaluation design.

## Current Hot Path

`process_span_batch()` persists spans and trace rows, commits the ingest
transaction, then enqueues three post-commit side effects:

1. `deliver_span_outbox_events.kiq(project_id=...)`
2. `update_trace_aggregates.kiq(...)` once per trace
3. `check_batch_anomalies.kiq(project_id=..., spans=spans)` once per processed
   batch

`check_batch_anomalies()` loads every active alert rule for the project:

```sql
SELECT id, name, metric, condition, threshold,
    cooldown_minutes, notify_slack_webhook, notify_email
FROM alert_rules
WHERE project_id = :project_id AND is_active = true
```

For every active windowed rule, it opens a project-scoped DB session and runs
one aggregate query over `spans`. Current windowed metrics are:

- `latency_p95`
- `error_rate`
- `cost_hourly`

Anomaly rules are evaluated per span through `AnomalyService.check()`.

## Current Complexity

For each processed ingest batch:

- alert rule load: `1` query
- windowed alert aggregations: `active_windowed_rules` queries
- anomaly checks: `active_anomaly_rules * spans_in_batch` service calls
- notification cooldown checks: only after a rule has already evaluated as
  triggered

That means the current cost is roughly:

```text
batches * (1 rule query + active_windowed_rules aggregate queries)
+ batches * active_anomaly_rules * spans_in_batch
```

The expensive part is not tied to the number of new spans that can affect a
window. A project with many active rules pays the same aggregate-query cost
after every batch, even when notification cooldown would suppress delivery.

## Query Shapes

Latency P95:

```sql
SELECT
    COALESCE(
        percentile_cont(0.95) WITHIN GROUP (ORDER BY latency_ms),
        0
    ) AS value,
    COUNT(*) AS sample_count
FROM spans
WHERE project_id = :project_id
    AND started_at >= NOW() - make_interval(mins => :window_minutes)
```

Error rate:

```sql
SELECT
    CASE WHEN COUNT(*) = 0 THEN 0
        ELSE (
            COUNT(*) FILTER (WHERE status = 'error')::float
            / COUNT(*)::float
        ) * 100
    END AS value,
    COUNT(*) AS sample_count
FROM spans
WHERE project_id = :project_id
    AND started_at >= NOW() - make_interval(mins => :window_minutes)
```

Hourly cost:

```sql
SELECT
    COALESCE(SUM(cost_usd), 0) AS value,
    COUNT(*) AS sample_count
FROM spans
WHERE project_id = :project_id
    AND started_at >= NOW() - make_interval(mins => :window_minutes)
```

Existing indexes support bounded project/time scans:

- `idx_spans_project_time` on `(project_id, started_at DESC)`
- `idx_spans_errors` on `(project_id, started_at DESC)` where
  `status = 'error'`

Block 02.3 already observed that bounded alert-style latency P95 queries prune
to eligible span partitions, but the current per-batch execution model still
scales poorly.

## Cooldown Finding

Cooldown lives inside `NotificationService.send_alert()`:

```text
alert_cooldown:<rule_id>
```

Because `check_batch_anomalies()` calls `send_alert()` only after the windowed
aggregate query triggers, cooldown cannot currently skip expensive SQL. A
scheduled evaluator should check cooldown before running the aggregate when the
rule only has notification side effects and no separate "record every
triggered state" requirement.

## EXPLAIN Status

Docker/Compose PostgreSQL was not available in this environment:

```bash
docker ps
# failed to connect to the docker API at unix:///var/run/docker.sock:
# connect: no such file or directory
```

Host-side DB-backed tests are also known to be unreliable in this runner when
the DSN resolves `postgres:5432`. Because of that, this mini-block records the
static query shapes and adds regression tests for the current query count and
cooldown ordering, but does not claim fresh `EXPLAIN ANALYZE` results.

Manual EXPLAIN command for an operator with local Compose:

```bash
docker compose -f infra/docker-compose.yml up -d postgres redis minio backend worker
docker compose -f infra/docker-compose.yml exec backend alembic upgrade head
docker compose -f infra/docker-compose.yml exec postgres psql -U llmobs_owner -d llmobs \
  -c "EXPLAIN (ANALYZE, BUFFERS) SELECT COALESCE(percentile_cont(0.95) WITHIN GROUP (ORDER BY latency_ms), 0) AS value, COUNT(*) AS sample_count FROM spans WHERE project_id = '<project-id>' AND started_at >= NOW() - make_interval(mins => 60);"
```

Use the same pattern for `error_rate` and `cost_hourly`, replacing the SELECT
body with the query shapes above.

## Recommended Scheduled Evaluation Design

Block 08.2 should move windowed alert evaluation out of the ingest hot path:

1. Add a periodic Taskiq task that scans active rules by project.
2. Apply a cooldown precheck before expensive aggregation where the only side
   effect would be notification delivery.
3. Evaluate each active rule on a bounded schedule, not after every batch.
4. Preserve project scoping by using `get_db(project_id=...)` for aggregation
   queries.
5. Keep anomaly rules separate until their per-span semantics are explicitly
   redesigned.

Block 08.3 should then move latency/error/cost evaluation toward incremental
time buckets so the scheduled evaluator does not repeatedly scan raw spans for
large windows.

## Regression Coverage

`backend/tests/integration/test_alert_rule_semantics.py` now covers:

- one aggregate SQL query per active windowed rule in
  `check_batch_anomalies()`;
- current cooldown ordering: aggregate SQL runs before notification cooldown
  code is reached.
