# ADR 0005 - Payload Storage And Metadata Policy

Date: 2026-07-28

## Status

Accepted.

## Context

LLM prompts, completions, system messages, headers and customer identifiers can
be sensitive. LLM Obs must support useful debugging without silently persisting
raw sensitive payloads in ordinary PostgreSQL fields.

The project previously had an ambiguous small-payload branch that omitted
payloads below the inline threshold instead of storing them consistently.

## Decision

Use explicit object storage for selected payloads:

- Project settings choose whether payload objects are stored for all spans,
  only failed spans or not stored.
- Payloads that are selected for storage and fit `payload_max_bytes` are
  redacted and written to MinIO/S3 as objects.
- PostgreSQL span rows store payload object keys and bounded storage status
  metadata, not raw prompt/output content.
- Payload loading in Trace Detail must remain an explicit user action.
- `payload_storage_mode=none` omits payload objects before object storage.
- S3/MinIO degradation does not block metadata ingest; affected spans record
  `payload_status=storage_failed`.

Span metadata persisted in PostgreSQL is restricted to a low-risk allowlist of
technical fields. Prompt, system, input/output, authorization-like and arbitrary
unknown metadata are dropped before persistence.

## Consequences

Backup and restore procedures must treat PostgreSQL and object storage as one
paired restore point. Restoring one without the other can produce missing
payload references or orphaned objects.

Operators should use payload status metrics and Trace Detail payload status
messages to distinguish policy omissions, oversized payloads and storage
failures.

Developers must route new provider metadata through the payload/redaction policy
or explicit safe fields instead of adding broad metadata persistence.

## Open Decisions

- Whether organization-level default payload policies should override project
  defaults.
- Whether selected payload objects should support per-object encryption keys in
  addition to the deployment's object-store encryption controls.
