# Roadmap And Known Limitations

This page separates what exists today from planned work. It should not be read
as a release promise.

## Current Capabilities

- Local and production Docker Compose deployments.
- Python SDK with decorator tracing and async OpenAI/Anthropic patching.
- OTLP HTTP trace ingest endpoint.
- Overview dashboard with latency, errors, cost and usage charts.
- Trace explorer and trace detail pages with explicit payload loading.
- Historical model pricing management.
- Alert rules and alert events with email or Slack targets.
- User invites, invite acceptance, role changes and guarded deletion.
- Project retention, payload privacy settings and API key management.
- Audit log for governance events.
- Prometheus metrics, health checks, runbooks and backup/restore docs.

## Known Limitations

- The dashboard uses one active project from the login session. A project
  switcher is not implemented yet.
- Frontend component/unit tests are not configured.
- Provider integration tests avoid real OpenAI and Anthropic credentials by
  default.
- Helm manifests are experimental and less exercised than Docker Compose.
- The dead-letter queue model exists, but retry/DLQ behavior still needs more
  production hardening.
- Payload privacy settings apply to stored payload objects. They do not replace
  upstream application-side secret handling.

## Planned Work

- Multi-project selection in the dashboard.
- Stronger retry/DLQ operator workflow.
- Mocked provider integration tests for OpenAI and Anthropic patching.
- Production-grade Kubernetes documentation and Helm hardening.
- Broader frontend test coverage once the UI flows stabilize.
- More detailed trace waterfall interactions and span comparison tools.
