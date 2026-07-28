# Roadmap And Known Limitations

This page separates what exists today from planned work. It should not be read
as a release promise.

## Current Capabilities

- Local and production Docker Compose deployments.
- Python SDK with decorator tracing and async OpenAI/Anthropic patching.
- OTLP HTTP trace ingest endpoint.
- Overview dashboard with latency, errors, cost and usage charts.
- Trace explorer and trace detail pages with explicit payload loading.
- Project selection and switching across projects visible to the signed-in user.
- Historical model pricing management.
- Alert rules and alert events with email or Slack targets.
- User invites, invite acceptance, role changes and guarded deletion.
- Project retention, payload privacy settings and API key management.
- Audit log for governance events.
- Prometheus metrics, health checks, runbooks and backup/restore docs.
- Frontend routed regression tests with Vitest, Testing Library and jsdom for
  critical dashboard flows.

## Known Limitations

- The dashboard has one active selected project at a time. Users can switch
  between projects they can access, but side-by-side multi-project comparison
  views are not implemented.
- Frontend tests are configured as routed Vitest tests. Browser E2E and
  automated accessibility/contrast checks are not configured.
- Provider integration tests avoid real OpenAI and Anthropic credentials by
  default.
- Helm manifests are experimental and less exercised than Docker Compose.
- The failed-task/DLQ surface is operator-visible and supports retry only for
  records that still contain a complete safe `process_span_batch` payload.
  Sanitized summary-only records are resolve-only; operators should resend from
  the original client when replay data is absent.
- Payload privacy settings apply to stored payload objects. They do not replace
  upstream application-side secret handling.
- Pricing records are currently global platform defaults guarded by
  `users.is_platform_admin`. The accepted target is a hybrid platform-default
  plus organization-override model documented in
  [ADR 0001](adr/0001-pricing-tenancy.md).

## Planned Work

- Side-by-side multi-project dashboard views and cross-project comparison.
- Stronger retry/DLQ operator workflow.
- Broader provider integration tests for OpenAI and Anthropic patching.
- Production-grade Kubernetes documentation and Helm hardening.
- Broader frontend coverage for remaining dashboard mutation errors, chart
  assertions and browser-level accessibility checks.
- More detailed trace waterfall interactions and span comparison tools.
