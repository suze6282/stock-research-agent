# ADR-003: Versioned Provider Adapter Pattern

- Status: Accepted for V0.1
- Date: 2026-07-11

## Decision

External sources are isolated behind versioned adapters. An adapter converts provider-specific payloads into a provider-neutral raw envelope; normalization and calculation occur in separate layers.

Required adapter behavior:

- typed input/output schema and explicit adapter version;
- timeout, bounded retry with jitter, provider-specific rate limiter and circuit breaker;
- no direct model access to credentials or raw database connections;
- source timestamps, retrieval time, checksum and provider request identifier;
- error taxonomy distinguishing invalid input, authorization, rate limit, unavailable, parse, incomplete and policy-blocked;
- immutable raw metadata/snapshot references without committing full raw responses to Git;
- contract tests using legally stored fixtures plus low-frequency live smoke tests.

Provider fallback is policy-driven and never silently merges facts. Conflicts are retained and escalated.

## Consequences

Adapters can later map to MCP without changing research semantics. A public website endpoint can remain a feasibility/cross-check adapter while being prohibited for production.
