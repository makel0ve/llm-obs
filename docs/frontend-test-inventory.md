# Frontend Test Inventory

Last updated: 2026-07-28.

Scope: Big Block 11.1, routed Vitest coverage for the React dashboard.

## Existing Coverage

- Auth shell: sign-in, registration, bootstrap token, disabled registration, invite acceptance and logout.
- Project access: no-access state, project tiles, project switcher, admin-only navigation and redirects from legacy routes.
- Organization settings: user invites, project assignment editing, implicit admin access, pricing create flow and audit-log navigation visibility.
- Project settings: scoped API-key creation, one-time reveal and failed-task retry eligibility.
- Alerts: rule creation and resolving open alert events.
- Traces list: loading, empty, error and data rows for the selected project.
- Overview: metrics cards and error-fingerprint analytics section.
- API/client hooks: dashboard JWT Authorization header and span SSE reconnect/cleanup behavior.

## Added In Block 11.1

- Trace Detail routed coverage for the selected trace, `started_at` query propagation and on-demand payload loading with redaction status.
- Audit Log routed coverage for filter submission and cursor-based pagination.

## Priority Gaps

- Dashboard/Overview: loading, empty and error states are partially covered; charts and tables still need focused assertions for timeseries, cost, latency and error breakdowns.
- Settings: payload privacy update, retention update, API-key rotate/revoke and mutation error states need routed tests.
- Alerts: update, pause/resume, validation failures and Slack-domain error copy need routed tests.
- Users: organization-user role changes, delete safeguards and project-access mutation failures need routed tests.
- Pricing: update/end flows, invalid date/cost validation and load-error state need routed tests.
- Trace Detail: error state, empty span state and payload requested but no object loaded should be covered before larger UI changes.
- Global UX: shared 401/403/429/5xx handling and Error Boundary behavior are intentionally left for Block 11.2.
- Accessibility/router: keyboard navigation, labels, dialog semantics, contrast and unused router dependency cleanup are intentionally left for Block 11.4.

## Test Helper Notes

- `frontend/src/test/App.test.tsx` currently owns the main dashboard API mock and routed user-flow setup.
- The file is getting large; future frontend slices should extract shared project/session factories and dashboard API mock defaults only when a new test needs them.
- Keep routed tests user-visible: assert headings, labels, recovery text and API call boundaries instead of component implementation details.
