# LLM Obs Frontend

React dashboard for the self-hosted LLM Obs stack. The app is built with Vite,
React Router, React Query, Tailwind CSS and typed API helpers under
`src/api/dashboard.ts`.

## Local Development

From the repository root, start the backend stack first:

```bash
cp backend/.env.example backend/.env
docker compose -f infra/docker-compose.yml up -d postgres redis redis-queue minio backend worker
docker compose -f infra/docker-compose.yml exec backend alembic upgrade head
```

Then run the frontend:

```bash
cd frontend
npm install
npm run dev
```

Vite serves the dashboard on `http://localhost:3000` by default. The frontend
expects the API at the configured Vite backend URL or the local backend default
used by `src/api/client.ts`.

## Scripts

```bash
npm run dev
npm run test
npm run lint
npm run build
npm run preview
```

- `dev` starts Vite with hot reload.
- `test` runs Vitest with Testing Library and jsdom.
- `lint` runs ESLint over the frontend source.
- `build` runs TypeScript project build and Vite production build.
- `preview` serves the built frontend locally.

## Application Shape

- `src/App.tsx` owns auth routing, project selection, admin route guards and
  lazy page loading.
- `src/pages/` contains dashboard pages: Overview, Traces, Trace Detail,
  Alerts, Project Users, Project Settings, Organization Settings, Pricing,
  Audit Log and invite acceptance.
- `src/api/dashboard.ts` contains typed dashboard API calls and React Query keys.
- `src/api/errors.ts` maps API, rate-limit, server, network and unknown errors
  into user-facing messages.
- `src/components/AppErrorBoundary.tsx` isolates route rendering failures.
- `src/components/TraceWaterfall.tsx` renders keyboard-operable trace spans.
- `src/hooks/useSpanStream.ts` manages the span SSE stream for the selected
  project.

## Testing

Current routed coverage lives mostly in `src/test/App.test.tsx`, with focused
tests for the API client, SSE hook and error boundary. Covered flows include:

- sign-in, registration, bootstrap-token and disabled-registration states;
- invite acceptance, logout and protected-route redirects;
- no-project access, project tiles and active project switching;
- admin-only navigation, organization users and project assignment flows;
- alerts, pricing creation/load errors and audit-log pagination/filtering;
- Project Settings API-key reveal and failed-task retry visibility;
- Trace Detail payload loading, empty spans and no-payload states.

The current inventory and remaining priority gaps are tracked in
`../docs/frontend-test-inventory.md`. Keep new tests user-visible: prefer
asserting route headings, labels, recovery text and API call boundaries over
component implementation details.

## Conventions

- Use `react-router-dom` for routing. `@tanstack/react-router` is intentionally
  not a dependency.
- Keep project-scoped pages behind the active project selected by the app shell.
- Keep organization-wide pages under `/admin-settings/*`.
- Route API calls through `src/api/dashboard.ts` or `src/api/client.ts` instead
  of creating ad hoc axios clients.
- Preserve explicit payload loading: Trace Detail should not auto-fetch stored
  prompt/output payloads.
- For new admin or mutation flows, add a routed Vitest regression when practical
  and update `../docs/frontend-test-inventory.md` if coverage priorities change.
