# Browser Token Storage Decision

Block 54 decision for the next hardening release.

## Decision

The dashboard may continue storing the login JWT in `localStorage` for the next
release. No server-side auth behavior changes are required in this block.

The current API contract is bearer-token based:

- `/v1/auth/register`, `/v1/auth/login` and invite acceptance return a JWT in
  the JSON response body.
- Browser dashboard requests send that JWT as `Authorization: Bearer ...`.
- The live span stream uses the same bearer token on reconnect.
- README examples document bearer JWTs for dashboard/admin API calls.
- Project ingest API keys remain separate from login JWTs.

Moving browser sessions to HttpOnly SameSite cookies is still a valid future
hardening direction, but it requires a migration plan for CORS, CSRF protection,
logout semantics, SDK/API examples and any external clients that currently use
bearer JWTs.

Block 07.5 keeps the bearer-token contract and hardens the browser delivery
path instead of introducing cookies mid-release. The production nginx frontend
now sends a restrictive CSP and browser security headers. The FastAPI backend
also sends non-CSP security headers on API responses; CSP is intentionally
owned by the frontend/reverse-proxy layer so development OpenAPI docs are not
broken by inline documentation assets.

## Risk

`localStorage` tokens are readable by injected JavaScript. A successful XSS issue
in the dashboard origin could exfiltrate the active login JWT until it expires or
the signing key is rotated.

## Current Mitigations

- Access tokens are signed JWTs with a configurable expiration
  (`JWT_ACCESS_TOKEN_EXPIRE_MINUTES`).
- Backend auth reloads the current user from the database on each request, so
  disabled, deleted or demoted users do not keep stale JWT privileges.
- Project API keys are separate credentials, hashed at rest and displayed once.
- Sensitive payload redaction defaults include `token` and `authorization`.
- Logout removes the browser token from `localStorage`.
- API clients receive bearer tokens explicitly and do not depend on ambient
  browser cookies.
- Production frontend responses include CSP, `X-Content-Type-Options`,
  `X-Frame-Options`, `Referrer-Policy` and `Permissions-Policy` headers.
- Backend API responses include non-CSP security headers that are safe for JSON
  API clients and development docs.

## Required Operating Controls

- Serve the dashboard only over HTTPS outside local development.
- Keep the dashboard and API behind trusted origins; do not allow untrusted
  scripts, browser extensions or user-authored HTML to execute in the dashboard
  origin.
- Keep token lifetime as short as practical for the deployment.
- Rotate `SECRET_KEY` if login JWTs may have been exposed.
- Treat an HttpOnly SameSite cookie migration as a separate breaking auth change
  with CSRF tests and a bearer-token compatibility plan.
- If the dashboard and API are split across different production origins, add
  that exact API origin to the frontend CSP `connect-src` directive; do not use
  a wildcard.
