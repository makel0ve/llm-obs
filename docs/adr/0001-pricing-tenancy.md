# ADR 0001 - Pricing Tenancy Model

Date: 2026-07-22

## Status

Accepted for implementation planning. Schema and authorization changes are
deferred to a dedicated migration block.

## Context

`model_pricing` is currently a global table. It has no `org_id`, and uniqueness
is scoped only by `(provider, model, valid_from)`.

The dashboard exposes Pricing under organization admin settings, while the
backend `/v1/pricing` API requires the separate `is_platform_admin` capability
on the current user row. Because the underlying catalog is global, this
capability is required to create, update or end prices used by every
organization.

Cost calculation happens during worker span processing. Workers receive only
the project id, then call `CostService` with provider, model, token counts and
span `started_at`. The pricing lookup currently has no project or organization
context.

This is acceptable for a single-organization self-hosted pilot, but it is not a
safe multi-organization ownership model.

## Decision

Use a hybrid pricing catalog:

- global platform default prices, owned by platform administrators;
- organization-scoped override prices, owned by organization administrators;
- worker lookup resolves the project organization, checks org-scoped prices
  first, then falls back to global defaults;
- historical interval semantics stay unchanged:
  `valid_from <= span.started_at` and `valid_to > span.started_at`.

Global pricing writes must require a new `platform_admin` boundary, separate
from organization `admin`.

Organization admins may manage only their own organization pricing overrides.
They must not mutate global platform defaults or other organizations'
overrides.

## Rationale

Global-only pricing is simple, but it makes any organization admin a de facto
platform administrator.

Org-only pricing isolates tenants, but it forces every organization to maintain
the full provider/model catalog and complicates first-run setup.

The hybrid model preserves easy defaults for self-hosted deployments while
adding a clear ownership boundary for multi-organization deployments and
customer-specific prices.

## Migration Plan

Implement in a later schema/API block:

1. Add platform-admin capability separate from `users.role`. Done for the
   current global pricing API through `users.is_platform_admin`.
2. Add nullable `org_id` to `model_pricing`.
3. Change uniqueness to include ownership:
   `(org_id, provider, model, valid_from)` for org overrides and a distinct
   global uniqueness boundary for `org_id IS NULL`.
4. Backfill existing rows as global defaults with `org_id = NULL`.
5. Update pricing APIs:
   - platform admins manage global defaults;
   - organization admins manage org-scoped overrides;
   - ordinary members/viewers cannot manage pricing.
6. Update worker cost lookup to resolve project organization and prefer
   org-scoped intervals before global intervals.
7. Update Redis pricing cache keys to include ownership context, for example
   `pricing:org:{org_id}:{provider}:{model}:active` and
   `pricing:global:{provider}:{model}:active`.
8. Add authorization tests for organization admin versus platform admin, plus
   lookup tests for org override fallback to global defaults.

## Current Compatibility

Until org-scoped overrides are implemented, the current API remains global and
guarded by `users.is_platform_admin`. Operators should assign this capability
only to trusted platform operators.

Existing pricing rows should remain valid as global defaults after migration.
Existing cost data stored on spans must not be recalculated retroactively.

## Consequences

The pricing tenancy implementation must update backend schema, API
authorization, worker lookup context, cache keys, frontend wording and docs
together. Partial implementation would either preserve cross-organization
mutation risk or break cost calculation for organizations without overrides.
