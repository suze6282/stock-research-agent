# HTTP API

The API keeps the existing configurable prefix; examples use the default
`/api/v1`. Database engines and Session factories are created only during the
application lifespan. Every request owns one Session, which is closed on both
success and failure. Importing the application does not connect to PostgreSQL.

## Resolve a security

```http
GET /api/v1/securities/resolve?query=MU
```

`query` is required and is limited to 1–256 characters at the HTTP boundary.
Safe resolution outcomes `RESOLVED`, `AMBIGUOUS`, and `NOT_FOUND` return
**HTTP 200** and are distinguished by the body `status`. Domain-invalid text
returns **HTTP 422** through the existing uniform error envelope.

Example body:

```json
{
  "status": "RESOLVED",
  "original_query": "MU",
  "normalized_query": "MU",
  "match_type": "EXACT_SYMBOL",
  "candidate_count": 1,
  "candidates": [
    {
      "security_id": "40000000-0000-0000-0000-000000000002",
      "issuer_id": "30000000-0000-0000-0000-000000000002",
      "issuer_display_name": "Micron Technology",
      "security_display_name": "Micron Technology",
      "symbol": "MU",
      "exchange_mic": "XNAS",
      "exchange_name": "Nasdaq",
      "market_code": "US_EQUITY",
      "currency_code": "USD",
      "listing_status": "UNKNOWN",
      "match_reason": "exact normalized symbol"
    }
  ],
  "warnings": ["A matched security has unknown listing status."]
}
```

Candidates are stable, bounded to ten, and have no confidence field.

## Security detail

```http
GET /api/v1/securities/{security_id}
```

The response contains security, issuer, exchange, market, identifiers, and
aliases only. It has no price, quote, financial, valuation, filing, or research
field. A malformed UUID returns **HTTP 422**; a valid missing UUID returns
**HTTP 404**.

## Issuer detail

```http
GET /api/v1/issuers/{issuer_id}
```

The response contains the issuer master record and confirmed issuer
identifiers. UUID error semantics match the security endpoint.

## Errors and correlation

Errors use the existing stable envelope:

```json
{
  "error": {
    "code": "INVALID_QUERY",
    "message": "Security query is invalid",
    "request_id": "..."
  }
}
```

Every response has `X-Request-ID`; a caller-supplied value is propagated.
Validation and operational errors do not expose SQL, table names, connection
strings, passwords, exception text, or tracebacks. The resolver performs no
external network request. OpenAPI is available at `/openapi.json` when enabled
by FastAPI defaults.

## Stage 4 persisted-data API

Stage 4 adds eight GET-only routes under `/api/v1`: `/data/providers`, latest and
history prices, corporate actions, raw financial facts, source-document metadata,
snapshot detail, and snapshot items. Exact paths and schemas are generated in
OpenAPI. All routes compose the shared read service and never ingest, refresh,
download, or build. Fixture evidence is `FIXTURE/OFFLINE/NOT_LIVE`; missing evidence
is `PARTIAL`. See [tool-contracts.md](tool-contracts.md) and
[data-snapshots.md](data-snapshots.md). No Stage 4 POST/PUT/PATCH/DELETE route exists.

## Stage 5 normalized-financial API

Stage 5 adds six bounded GET-only routes under the existing `/api/v1` prefix:

```text
GET /securities/{security_id}/financial-periods?snapshot_id=...
GET /securities/{security_id}/normalized-financial-facts?snapshot_id=...
GET /securities/{security_id}/financial-metrics?snapshot_id=...
GET /securities/{security_id}/financial-metrics/{metric_code}?snapshot_id=...
GET /calculation-runs/{calculation_run_id}
GET /calculation-runs/{calculation_run_id}/lineage?metric_code=...
```

The normalized-facts path is deliberately distinct from Stage 4's raw
`/financial-facts` route. Invalid UUID/query/limit input returns 422; a missing
snapshot or calculation run returns a safe 404; a valid calculation that lacks
evidence returns HTTP 200 with typed `PARTIAL` or `BLOCKED`, `NULL`/`N/M`, and
warnings. Responses preserve request IDs and fixture provenance and never expose
SQL, storage paths, connection strings or exceptions.

All six routes call the same read-only Tool/query service as the CLI. There is no
normalize, calculate, ingest, refresh, mapping mutation, formula mutation, POST,
PUT, PATCH or DELETE route. OpenAPI generation is covered offline.
# Stage 6 read-only routes

Stage 6 adds eight GET-only document/RAG routes under the existing `/api/v1` prefix. `/rag/search`
uses exact security plus snapshot or as-of scope and reads only precomputed results. Business
BLOCKED/PARTIAL outcomes use HTTP 200; invalid parameters use the existing safe 422 envelope.
Citation verification and other scoped reads require exactly one Snapshot or timezone-aware as-of
value. Detail misses use the safe 404 envelope. There is no parse, index, embedding,
retrieval-write, download or refresh HTTP route.
# Stage 7 controlled research reads

The existing API prefix exposes eight GET-only endpoints for run, Plan, steps,
Tool invocations, Evidence, Claims, package, and events. There are no POST,
PUT, PATCH, or DELETE research endpoints. Missing resources return safe 404
responses; invalid UUID, limit, or offset returns 422. Responses preserve the
request ID and never disclose SQL, local storage paths, credentials, or raw
Evidence payloads. API reads do not execute or resume a run and perform no
implicit network refresh.

# Stage 8 report reads

Stage 8 adds ten GET-only routes under `/api/v1/research-reports`: report detail,
sections, Claim bindings, Evidence bindings, Citation bindings, Reflection runs,
Findings, Revision runs, Release Gate and versions. Collection routes use
bounded `limit`/`offset`.

The routes read only persisted results. A cache miss is a safe 404; validation
is 422 using the existing request-ID error envelope. GET never generates a
report, executes Reflection or Revision, evaluates a Gate, reruns Research,
refreshes data, calls a Tool/provider/model, or accesses the network. Responses
exclude raw documents, full Package payloads, local storage paths and secrets.
# Stage 9 Provider GET API

The existing prefix exposes only the approved reads, including `GET /providers`,
`GET /providers/{provider_code}`, capabilities/health/license, bounded Run
requests/artifacts/quality-issues/dead-letters, and
`GET /provider-readiness/{security_id}`. Pagination is capped at 100, unknown sort
or control parameters return 422, missing resources return a safe 404, and
`X-Request-ID` is retained.

Provider `POST` sync/live-check/repair/credential routes are forbidden, as are
PUT, PATCH and DELETE. GET never probes, syncs, repairs, downloads or returns raw
payloads, headers, secrets, local storage paths, connection strings or SQL. A
persisted business `BLOCKED` state remains HTTP 200 data.

# Stage 10 Gate A GET-only API

The `/api/v1/live-evidence` prefix exposes ten GET-only projections for finite
authorizations, authorization events/consumptions, execution approvals, manual
imports, ingestion manifests, validation runs/checks, incidents and incident
events. Singular resources use exact row IDs; list resources use their approved
parent ID plus bounded, stable `limit`/`offset` ordering.

All corresponding Tools are `READ_ONLY`, `writes=false`, and
`requires_network=false`. API and Tools cannot create or activate a Grant, run SEC,
read a Credential, import a file, create a Snapshot, execute Agent/Report work, or
trigger a refresh. Missing rows return safe 404, invalid input returns 422, and
responses exclude SQL, connection strings, local paths, secrets, restricted bytes
and unbounded payloads. No Stage 10 POST/PUT/PATCH/DELETE route exists.
