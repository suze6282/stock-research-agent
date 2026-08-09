# Tool Use Design V0.1

## Registry and contract

Every tool is registered with `tool_name`, semantic `tool_version`, purpose, owner, allowed caller, read/write class, input/output JSON Schema, timeout, retry policy, rate bucket, cache policy, idempotency key, provider/source, cost class, data classification and audit policy. Unknown tools are denied.

Tool responses use a common envelope:

```json
{
  "ok": true,
  "tool_name": "get_daily_close",
  "tool_version": "1.0.0",
  "request_id": "...",
  "data": {},
  "source": {"provider": "...", "source_id": "...", "url": "..."},
  "timing": {"source_published_at": "...", "retrieved_at": "..."},
  "snapshot_id": "...",
  "warnings": [],
  "error": null
}
```

Errors are typed: `INVALID_INPUT`, `NOT_FOUND`, `AUTH_REQUIRED`, `FORBIDDEN`, `RATE_LIMITED`, `TIMEOUT`, `UPSTREAM_UNAVAILABLE`, `PARSE_ERROR`, `INCOMPLETE_DATA`, `AS_OF_VIOLATION`, `POLICY_BLOCKED`, `CONFLICT` and `INTERNAL_ERROR`. Errors never contain secrets or unbounded raw payloads.

## Permission classes

| Class | Examples | V0.1 Agent access |
|---|---|---|
| `READ_PUBLIC_SOURCE` | filing metadata, whitelisted document fetch, daily close | Allowed only for approved domains and fixed security/cutoff |
| `READ_SNAPSHOT` | normalized facts, calculations, retrieved chunks | Allowed through narrow query tools |
| `COMPUTE_DETERMINISTIC` | TTM, metrics, scenario valuation | Fixed pipeline only; Agent receives results |
| `WRITE_INTERNAL_SNAPSHOT` | persist fetched artifact metadata/facts | Fixed pipeline service account only |
| `ADMIN` | provider config, secrets, migration, allowlist | Never available to Agent |
| `EXTERNAL_SIDE_EFFECT` | email, order, broker, arbitrary upload | Not registered in V0.1 |

Tools never expose environment variables, secret stores, filesystem browsing, shell execution, arbitrary SQL or arbitrary URLs to the model. Credentials remain inside the adapter runtime.

## Reliability controls

- **Timeout:** connect/read/overall values per provider; no unbounded request.
- **Retry:** only transient, idempotent reads; exponential backoff with jitter and maximum attempts. Do not retry invalid input/auth/policy errors. Respect `Retry-After`.
- **Rate limit:** provider-specific token bucket below published ceilings; SEC internal target should be materially below 10 requests/second and use bulk/caching.
- **Cache:** key includes provider, endpoint semantics, security, parameters and as-of; TTL follows data mutability. Immutable filing accessions/content hashes are content-addressed.
- **Idempotency:** read tools are naturally idempotent for frozen snapshot parameters; writes require an idempotency key and unique constraint.
- **Circuit breaker:** repeated upstream failures stop calls and return a degraded result.
- **Logging:** request ID, tool/version, caller, normalized parameters hash, provider, status, latency, bytes, cache hit, retry count, cost, snapshot and redacted error. Never log token/header/raw confidential content.

## Initial tool boundary (design only)

| Tool contract | Called by fixed flow | Limited Agent call | Notes |
|---|---:|---:|---|
| `resolve_security(query, as_of)` | Yes | No | Identity must finish first. |
| `get_market_calendar(exchange, range)` | Yes | No | Determines completed sessions. |
| `get_daily_close(security_id, market_date)` | Yes | No | ADR-008 semantics. |
| `get_financial_facts(security_id, periods, as_of)` | Yes | No | Provider-neutral raw/normalized lineage. |
| `get_corporate_actions(security_id, range, as_of)` | Yes | No | Required for shares/adjustment. |
| `list_filings(security_id, form_types, as_of)` | Yes | Yes, narrowed | Agent cannot change security/cutoff. |
| `retrieve_evidence(security_id, query, filters)` | Yes | Yes | Filters are intersected with run policy. |
| `get_citation(citation_id)` | Yes | Yes | Returns exact passage/location. |
| `calculate_metrics(snapshot_id, formula_version)` | Yes | No | Deterministic service only. |
| `calculate_scenarios(snapshot_id, assumptions)` | Yes | No | Schema-valid assumptions; results labeled scenario. |
| `validate_report(report_id)` | Yes | No | Reflection gate. |

## Source and data policy

Every tool response names the original provider and evidence URL/identifier. A fallback is a new provenance branch, not a transparent substitution. Provider conflicts remain visible. Public website endpoints marked `PARTIALLY_VERIFIED` are disabled for production until terms and stability are accepted.

## Tests required later

Schema contract, timeout, retry/non-retry, 429 handling, cache key, idempotency, as-of rejection, allowlist rejection, secret redaction, error envelope, circuit breaker, provider conflict and Agent permission tests.
