# Partition Pruning Audit

Date: 2026-07-21

Scope: Big Block 02, Block 02.3. The audit covers trace list/detail, overview
metrics, analytics and retention queries against the local Docker Compose
PostgreSQL database.

## Dataset

The local database was upgraded to the current Alembic head before EXPLAIN:

```bash
docker compose -f infra/docker-compose.yml exec backend alembic upgrade head
```

Observed dataset:

| Table | Rows |
| --- | ---: |
| `spans` | 13,044 |
| `traces` | 5,138 |

Observed partitions:

| Parent | Partitions |
| --- | --- |
| `spans` | `spans_2026_05`, `spans_2026_06`, `spans_default` |
| `traces` | `traces_2026_05`, `traces_2026_06`, `traces_default` |

Most current rows are in the default partitions:

| Partition | Rows | Time range |
| --- | ---: | --- |
| `spans_2026_06` | 121 | 2026-06-05 to 2026-06-30 |
| `spans_default` | 12,923 | 2026-07-01 to 2026-07-16 |
| `traces_2026_06` | 26 | 2026-06-05 to 2026-06-30 |
| `traces_default` | 5,112 | 2026-07-01 to 2026-07-16 |

Audit project:

| Project spans | Time range |
| ---: | --- |
| 226 | 2026-07-02 to 2026-07-07 |

## Findings

### Time-Bounded Trace List

Query shape:

```sql
SELECT id, project_id, started_at, ended_at, total_tokens,
    total_cost_usd, span_count, status
FROM traces
WHERE project_id = :project_id
  AND started_at >= :from_dt
  AND started_at <= :to_dt
ORDER BY started_at DESC, id DESC
LIMIT :limit
```

Finding: partition pruning works when the request includes a time range. The
July query scanned only `traces_default` and used
`traces_default_project_id_started_at_idx`.

Observed plan summary:

- `Bitmap Index Scan on traces_default_project_id_started_at_idx`
- no `Append` across older trace partitions
- execution time in local dataset: about 31 ms on the first cold-ish run

### Default Trace List Without Time Filters

Query shape:

```sql
SELECT id, project_id, started_at, ended_at, total_tokens,
    total_cost_usd, span_count, status
FROM traces
WHERE project_id = :project_id
ORDER BY started_at DESC, id DESC
LIMIT :limit
```

Finding: without `started_at` bounds, PostgreSQL must append all trace
partitions. Each child still uses a project/time index, but every partition is
eligible.

Observed plan summary:

- `Append`
- scans `traces_2026_05`, `traces_2026_06` and `traces_default`
- execution time in local dataset: about 0.1 ms, but this cost will grow with
  more historical partitions

Follow-up: add a default time window for trace list or require/persist a user
selected time range in the dashboard. The API should keep an explicit escape
hatch for all-history searches.

### Trace Detail Lookup Without `started_at`

Query shape:

```sql
SELECT started_at
FROM traces
WHERE id = :trace_id AND project_id = :project_id
ORDER BY started_at ASC
LIMIT 1
```

Finding: the lookup used by `GET /v1/traces/{trace_id}` when the caller omits
`started_at` cannot prune partitions, because `started_at` is unknown. The plan
used `Merge Append` across all trace partitions before finding the row.

Observed plan summary:

- `Merge Append`
- scans `traces_2026_05`, `traces_2026_06` and `traces_default`
- execution time in local dataset: about 39 ms on the first cold-ish run

When `started_at` is supplied, pruning works:

- scans only `traces_default`
- uses `traces_default_project_id_started_at_idx`
- execution time in local dataset: about 0.06 ms

Follow-up: make trace detail links include `started_at` from trace list rows and
prefer the `started_at` query parameter in frontend navigation.

### Trace Detail Spans

Query shape:

```sql
SELECT id, trace_id, parent_span_id, name, provider, model,
    input_tokens, output_tokens, cost_usd, latency_ms,
    status, error, started_at, payload_s3_key, payload_status,
    payload_drop_reason, metadata
FROM spans
WHERE trace_id = :trace_id
  AND project_id = :project_id
  AND started_at >= :started_at
ORDER BY started_at ASC
```

Finding: with `started_at` from the trace row, pruning works. The July detail
query scanned only `spans_default` and used
`spans_default_trace_id_started_at_idx`.

Observed plan summary:

- `Index Scan Backward using spans_default_trace_id_started_at_idx`
- execution time in local dataset: about 3 ms

### Metrics And Analytics

Covered query shapes:

- overview aggregates over `spans`
- timeseries bucket aggregates over `spans`
- cost by model
- top expensive traces
- recent failed traces
- alert-style latency P95 window

Finding: queries with `started_at >= :cutoff` or `started_at >= NOW() -
interval` prune correctly to the eligible span partitions. They use
`spans_default_project_id_started_at_idx` for broad aggregates and the partial
`spans_default_project_id_started_at_idx1` index for `status = 'error'`.

Observed plan summaries:

- overview: `Bitmap Heap Scan on spans_default`, execution about 31 ms on the
  first cold-ish run
- timeseries: `Bitmap Heap Scan on spans_default`, execution about 0.3 ms
- cost by model: `Bitmap Heap Scan on spans_default`, execution about 0.2 ms
- top expensive traces: `Bitmap Heap Scan on spans_default`, execution about
  0.2 ms
- recent failed traces: partial error index, execution about 0.8 ms
- alert latency P95 for the last 24h: runtime partition pruning removed two
  subplans and scanned only `spans_default`

Follow-up: no immediate index rewrite is needed for the audited bounded
metrics/analytics queries. Later scale work should move expensive percentile and
group-by aggregates to incremental buckets, as planned in Big Block 08.

### Retention Select

Query shape:

```sql
SELECT id, started_at, payload_s3_key
FROM spans
WHERE project_id = :project_id
  AND started_at < :cutoff
ORDER BY started_at ASC
LIMIT :limit
```

Finding: retention uses an upper-bound-only time predicate. PostgreSQL must
consider all partitions earlier than the cutoff, which is expected for data
expiration. Child partition indexes are used where the planner considers them
beneficial; the small June partition used a sequential scan in the local
dataset.

Observed plan summary for cutoff `2026-07-05`:

- `Append`
- scans May, June and default span partitions
- uses `spans_default_project_id_started_at_idx` for the default partition
- execution time in local dataset: about 0.1 ms

Follow-up: this query is acceptable for retention semantics, but Block 02.4
should prevent current-month data from accumulating in `spans_default`.

### Retention Composite-Key Delete

Query shape:

```sql
WITH selected_spans AS (
    SELECT id::uuid, started_at::timestamptz
    FROM jsonb_to_recordset(CAST(:span_keys AS jsonb))
        AS selected(id text, started_at text)
)
DELETE FROM spans
USING selected_spans
WHERE spans.project_id = :project_id
  AND spans.id = selected_spans.id
  AND spans.started_at = selected_spans.started_at
```

Finding: the composite-key delete is logically correct, but the current
`jsonb_to_recordset` shape does not allow PostgreSQL to statically prune
partitions in the observed plan. The non-destructive `EXPLAIN` showed delete
targets for May, June and default partitions.

Follow-up: if retention delete becomes expensive with many partitions, consider
deleting per partition/time bucket or using a bounded `started_at` range in the
delete statement in addition to exact `(id, started_at)` matching.

## Recommended Follow-Up Blocks

1. Block 02.4 should create future monthly partitions ahead of time and alert on
   default partition growth. The local dataset already shows July data in
   `spans_default` and `traces_default`.
2. Add a trace-detail navigation follow-up: include `started_at` in frontend
   trace links and API callers so detail lookup avoids all-partition `Merge
   Append`.
3. Add a trace-list time-window follow-up: default dashboard trace list to a
   bounded time range while preserving explicit all-history search.
4. Keep metrics/analytics index rewrites out of Big Block 02 for now; audited
   bounded queries prune correctly. Revisit aggregate cost in Big Block 08 when
   scheduled evaluation and incremental buckets are in scope.
