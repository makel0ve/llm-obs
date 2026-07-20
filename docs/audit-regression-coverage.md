# Audit Regression Coverage

Block 55 inventory for high-risk regressions covered by the hardening plan.

## Coverage Map

- Redis durability and idempotency: batch status, enqueue failure, atomic
  idempotency reservation, body mismatch and concurrent duplicate requests are
  covered in `backend/tests/integration/test_ingest_batch_status.py`.
- Task queue durability wiring: `backend/tests/unit/test_taskiq_dlq.py` verifies
  that the Taskiq broker, result backend and DLQ broker use
  `settings.effective_redis_queue_url`.
- OTLP IDs: `backend/tests/integration/test_otlp_api.py` covers OTLP hex ID
  normalization, malformed ID rejection and partial success reporting.
- Cursor pagination: `backend/tests/unit/test_trace_cursor.py` and
  `backend/tests/integration/test_traces_api.py` cover encoded cursors,
  timestamp delimiter compatibility and invalid cursor rejection.
- Non-superuser RLS/runtime role: `backend/tests/unit/test_config.py` covers
  production rejection of owner or `postgres` runtime database users; deployment
  runbooks document `NOSUPERUSER NOBYPASSRLS` checks.
- Out-of-order spans and repeated batches:
  `backend/tests/integration/test_traces_api.py` covers stable logical trace
  identity and duplicate trace-row prevention.
- Historical pricing:
  `backend/tests/integration/test_cost_service.py` covers historical pricing
  cache keys and reuse by lookup time.
- Retention:
  `backend/tests/integration/test_retention.py` covers payload object deletion,
  project-scoped DB cleanup, stale trace cleanup and keeping spans when object
  deletion fails.
- Notification cooldown:
  `backend/tests/integration/test_notifications.py` covers failed delivery not
  recording cooldown, successful delivery recording cooldown and existing
  cooldown suppressing delivery.
- JWT role changes:
  `backend/tests/integration/test_auth_current_user.py` covers disabled/deleted
  user rejection, latest DB role loading and project access using the current
  role instead of a stale JWT role.

## Remaining Boundary

Production Compose Redis persistence, image pinning, port exposure and service
health/resource checks are intentionally left to the dedicated production
deployment blocks that follow this coverage inventory.
