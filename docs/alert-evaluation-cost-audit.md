# Alert Evaluation Cost Audit

Date: 2026-07-22

Scope: Big Block 08.1, observed alert evaluation hot path and recommended
scheduled evaluation design.

## Block 08.1 Observed Hot Path

Before Block 08.2, `process_span_batch()` persisted spans and trace rows,
committed the ingest transaction, then enqueued three post-commit side effects:

1. `deliver_span_outbox_events.kiq(project_id=...)`
2. `update_trace_aggregates.kiq(...)` once per trace
3. `check_batch_anomalies.kiq(project_id=..., spans=spans)` once per processed
   batch

At that point, `check_batch_anomalies()` loaded every active alert rule for the
project:

```sql
SELECT id, name, metric, condition, threshold,
    cooldown_minutes, notify_slack_webhook, notify_email
FROM alert_rules
WHERE project_id = :project_id AND is_active = true
```

For every active windowed rule, it opened a project-scoped DB session and ran
one aggregate query over `spans`. Windowed metrics were:

- `latency_p95`
- `error_rate`
- `cost_hourly`

Anomaly rules are evaluated per span through `AnomalyService.check()`.

## Block 08.1 Observed Complexity

Before Block 08.2, each processed ingest batch paid:

- alert rule load: `1` query
- windowed alert aggregations: `active_windowed_rules` queries
- anomaly checks: `active_anomaly_rules * spans_in_batch` service calls
- notification cooldown checks: only after a rule has already evaluated as
  triggered

That meant the cost was roughly:

```text
batches * (1 rule query + active_windowed_rules aggregate queries)
+ batches * active_anomaly_rules * spans_in_batch
```

The expensive part was not tied to the number of new spans that could affect a
window. A project with many active rules paid the same aggregate-query cost
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

Before Block 08.2, `check_batch_anomalies()` called `send_alert()` only after
the windowed aggregate query triggered, so cooldown could not skip expensive
SQL. The scheduled evaluator now checks cooldown before running the aggregate
when the rule only has notification side effects and no separate "record every
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

## Block 08.2 Follow-Up

Block 08.2 implemented the first scheduled evaluation step: windowed alert
rules now run from a periodic Taskiq scheduler task, and the ingest batch hot
path no longer evaluates latency, error-rate or cost windows after every batch.
The scheduled path prechecks notification cooldown before running the aggregate
query. Per-span anomaly checks remain batch-scoped because their current
semantics depend on the spans that were just processed.

Incremental time buckets remain planned for Block 08.3.

## Regression Coverage

`backend/tests/integration/test_alert_rule_semantics.py` now covers:

- batch hot path ignores windowed rules and keeps only anomaly selection;
- one aggregate SQL query per active windowed rule in the scheduled evaluator;
- scheduled cooldown precheck skips aggregation SQL when a rule is already on
  cooldown.
