# Architecture Boundaries

This document records the current import boundaries used to keep the FastAPI
backend maintainable as the API, service and worker layers evolve.

## Target Boundaries

- API modules in `backend/app/api` own HTTP concerns: routing, dependency
  injection, request parsing, response shaping and authorization checks.
- API modules should call service interfaces for storage, queue, cache and
  worker behavior instead of importing implementation details directly.
- Service modules in `backend/app/services` own business operations and may
  depend on Redis clients, storage clients and database access when those
  dependencies are part of the operation.
- Worker modules in `backend/app/workers` own Taskiq execution, retry/DLQ
  behavior, retention jobs and direct queue processing.
- Model modules in `backend/app/models` should stay persistence-only and should
  not import API, worker or storage client modules.

## Guardrail

`backend/tests/unit/test_architecture_boundaries.py` parses API modules with
`ast` and blocks new API imports of implementation-detail modules:

- `aioboto3`, `boto3` and `botocore`
- `redis.asyncio`
- `app.core.redis`
- `app.services.storage`
- `app.workers`

The test includes a narrow allowlist for current compatibility exceptions:

- health checks read Redis and worker heartbeat status directly.
- readiness checks call the payload storage bucket check directly.
- metrics endpoints use Redis for response caching.
- OTLP ingest constructs the ingest service with a Redis dependency.
- pricing/project key rotation endpoints invalidate Redis cache keys directly.
- failed-task retry currently calls the worker task entry point.
- trace detail payload loading calls the payload storage service directly.

These exceptions should shrink when the corresponding behavior moves behind
service-layer interfaces. New API endpoints should not add to the allowlist
without documenting why the service boundary cannot handle the dependency.
