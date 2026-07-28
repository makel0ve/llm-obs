# Frontend Router And Accessibility Audit

Last updated: 2026-07-28.

Scope: Big Block 11.4, router dependency and dashboard accessibility checks.

## Router Dependency Findings

- The frontend uses `react-router-dom` for `BrowserRouter`, `Routes`, `Route`, `Navigate`, `NavLink`, `Outlet`, `Link`, `useNavigate`, `useParams`, `useSearchParams` and test `MemoryRouter`.
- No source file imports `@tanstack/react-router`.
- `@tanstack/react-router` was removed from `frontend/package.json` and `frontend/package-lock.json` to reduce bundle and maintenance surface.

## Accessibility Findings

- Dashboard and organization navigation already expose nav landmarks through `aria-label`.
- Project switcher already exposes an `Active project` label through screen-reader-only text.
- Organization Users delete confirmation already uses `role="dialog"`, `aria-modal="true"` and `aria-labelledby`.
- Most project, alert, pricing, audit and user forms have explicit visible labels.
- The auth form relied on placeholders for Email, Password, Organization name and Bootstrap token. These fields now have screen-reader labels while preserving the compact visual layout.
- The legacy `TraceWaterfall` span rows were clickable `div` elements. They are now keyboard-focusable buttons with expand/collapse labels and pressed state.

## Remaining Follow-Ups

- Run a browser-based keyboard pass on the project switcher, organization settings tabs, Users delete dialog and Trace Detail payload toggle before a release candidate.
- Consider a dedicated accessibility test tool such as axe after the test stack has a stable browser runner.
- Contrast is acceptable for the current Tailwind gray/blue/red/amber states by inspection, but no automated contrast audit is configured yet.
