# Stage 10 Gate B Enablement Step 1B Design

Status: **DESIGN COMPLETE — IMPLEMENTATION NOT STARTED**

Gate B readiness remains **NO_GO**. Gate B is not authorized or executed, and
Stage 11 has not started. This report resolves the two Step 1A contract gaps and
defines the smallest offline implementation slices. It does not freeze a filing,
resolve contact configuration, open a socket, or change production code.

## 1. Fixed inputs

The source baseline is commit `3684475d5d114a29ba8c301203f5ae58d64dc4c2`
on `test/stage-10-gate-b-enablement-red`. The following Step 1A contracts are
already GREEN and must not be redesigned: RED-030, RED-033, RED-040, RED-041,
RED-042, RED-047, and RED-048.

The remaining production-composition REDs are RED-028, RED-029, RED-031,
RED-032, RED-034 through RED-039, RED-043, RED-044, RED-046, and RED-049.
RED-045 is a transaction-boundary testability gap.

## 2. Contact identity contract

### 2.1 Repository finding

The committed design uses the phrase `DECLARED_CONTACT_IDENTITY` as a resolver
kind. The implementation and PostgreSQL contract, however, expose only `NONE`
and `ENVIRONMENT`; the `provider_credential_references` CHECK constraint and
the 16-character column cannot store the proposed 25-character enum value.

The database already has the information required to distinguish the SEC
contact role without another resolver kind:

- a secret-free credential reference with resolver kind `ENVIRONMENT` and
  declared name `SEC_EDGAR_CONTACT_IDENTITY`;
- `LiveAuthorizationGrant.user_agent_reference_id`, which binds that reference
  to the request-identity role;
- provider, reference, declared-name, license, configuration, and live-grant
  gates in `EnvironmentCredentialResolver`.

Therefore `DECLARED_CONTACT_IDENTITY` is resolved here as a **transient binding
role**, not a persisted resolver mechanism. The persisted mechanism remains
`ENVIRONMENT`. This clarification supersedes the over-specific wording in the
Stage 10 design and preparation report; it does not weaken the no-secret
contract and requires no schema change. RED-038 must test the runtime formatter
and redaction behavior, not the presence of a new database enum.

### 2.2 Internal candidate contract

The exact current SEC policy and preferred contact string format are deliberately
not asserted offline. Before Gate B authorization, primary SEC policy must be
freshly re-verified and the approved resolved value frozen through the existing
reference mechanism.

The internal candidate contract is:

1. Persist only the credential reference, safe label, version, status, declared
   name, and the grant's `user_agent_reference_id`.
2. Treat the resolved value as the complete, externally approved User-Agent
   field value. Do not synthesize an email, URL, product name, or other provider
   policy claim offline.
3. Resolve it once, at execution time, after authorization, approval, plan,
   provider, candidate, budget, host, path, and method gates pass and before DNS
   or socket creation.
4. Hold it only in an ephemeral, non-serializable object with redacted
   `repr`/`str`. Reject empty values, values longer than 256 characters, CR/LF,
   DEL, and other control characters.
5. Permit that object to disclose the value only to the final protected
   `User-Agent` header emission inside the SEC transport boundary.
6. Never place the value, a hash, prefix, suffix, header dump, or derived fragment
   in a checksum, plan, grant, exception, structured log, audit row, artifact
   metadata, or return payload.

`HttpClientPolicy.user_agent` is currently a printable string and therefore is
not an acceptable container for the resolved value. The minimal production
change is a typed redacted request-identity material accepted by the HTTP client
and unwrapped only while creating the protected header. Arbitrary request
headers remain unable to override `User-Agent`.

### 2.3 Ownership and RED boundary

The unique resolution owner is the SEC transport composition. The authorization
factory validates and binds reference metadata only. The request planner and
request builder never read the environment. The HTTP client emits the protected
header but does not resolve credentials.

- RED-031 tests production composition of the reference plus absence of resolved
  material from grants, checksums, audit, logs, exceptions, and returned values.
- RED-038 tests an injected fake resolver producing ephemeral identity material,
  its conversion to the protected HTTP request identity, validation/redaction,
  and absence of leakage. It must not assert a new persisted resolver enum.

## 3. Reservation / Settlement Transaction Model

Repositories are transaction-neutral and accept caller-owned SQLAlchemy
sessions. Existing live-consumption code already reserves one request under an
authorization row lock before socket creation. The final ordering is a
Pre-request Reservation Transaction and a Post-response Settlement Transaction
around a transaction-free network window:

1. Validate authorization, execution approval, candidate, immutable plan, and
   the deterministic request.
2. Preallocate one `request_attempt_id`.
3. Begin the short Pre-request Reservation Transaction; revalidate grant state
   and budgets, atomically reserve `(authorization_id, request_attempt_id)` and
   any retry eligibility, then commit.
4. Resolve the contact identity, enforce the final request policy, and perform
   DNS/send/stream/response validation with **no database transaction open**.
5. Build checksum and provenance outside the database transaction. Write bytes
   through the existing atomic temporary/final blob protocol.
6. Begin the short Post-response Settlement Transaction. Settle consumption and
   persist the request-attempt audit for every outcome. On a validated success,
   persist the Raw Artifact, manifest, and checkpoint together where their
   lineage requires atomicity. Commit.
7. Continue deterministic DocumentVersion, parse/chunk, Citation, and Data
   Quality work in bounded caller-owned transactions, then stop.

The reservation transaction is intentionally before the network operation; it
is short and prevents concurrent overspend. It is not an ingestion transaction
and must be committed before credential resolution, DNS, or send.

This model is **not** a distributed Two-Phase Commit or 2PC protocol. Blob
storage and PostgreSQL do not share one atomic commit coordinator.

### 3.1 Attempt identity and failure audit

The same preallocated UUID must identify the authorization consumption, the
terminal `ProviderRequestAttempt`, and the Raw Artifact foreign key. The current
attempt repository allocates its ID internally, so Step 1B-3 needs a small
interface change allowing an application-supplied attempt UUID. No database
column or constraint changes are needed.

DNS, connection, timeout, and HTTP failures receive a terminal attempt row and
consumption settlement in the Post-response Settlement Transaction even though
no Raw Artifact exists. If audit cannot prove that no socket opened before a
crash and settlement, the committed reservation remains consumed and blocks
continuation until explicit reconciliation; it is never silently refunded.

Once the Pre-request Reservation Transaction commits, a later contact-identity,
final-policy, local-validation, pre-DNS, or pre-socket application failure cannot
return the attempt to an unused state. The application must persist a terminal,
auditable non-success outcome. `ABANDONED` is permitted only through the existing
settlement contract with `socket_opened=False` and `actual_bytes=0`; uncertainty
about either fact cannot be classified as `ABANDONED`.

An explicitly settled `ABANDONED` row remains permanent audit lineage. The
existing request-budget query excludes that state, so a successful, explicit
settlement/reconciliation decision can reclaim request capacity. That accounting
result is not an automatic refund of the attempt, retry token, execution
approval, or human authorization:

- the `request_attempt_id` and its attempt number remain consumed and cannot be
  reused;
- a reserved retry token remains consumed even when the retry never reaches a
  socket;
- the failed Gate B pilot becomes a terminal non-success; the same single-use
  execution approval cannot restart it;
- another execution requires the existing explicit reconciliation outcome and a
  new valid grant/plan-bound single-use approval. No application component can
  infer replay permission merely from `ABANDONED` or reclaimed request capacity.

These fail-closed rules remove implicit refund behavior. Any future relaxation
requires a separately approved authorization/reconciliation contract; it is not
part of Step 1B.

### 3.2 RED-045 testability

The SEC pilot application will receive one production-neutral transaction
factory protocol. Each invocation returns a bounded unit of work containing the
required repositories. Production wraps the existing SQLAlchemy session scope;
tests inject an instrumented fake. No test-only flag or production event logger
is required.

The fake records both the initial-attempt and retry paths:

`authorization_validated -> request_built -> reservation_begin ->
reservation_commit -> send_start -> send_complete -> persistence_begin ->
attempt/artifact_persisted -> persistence_commit`

The fake transport asserts that its transaction factory reports no active unit
of work at `send_start` and `send_complete`. A retry trace must additionally
show `retry_eligibility_checked` and `retry_reserved` before
`reservation_commit`; a rejected retry must have no `dns_start` or `send_start`
event. RED-045 also tests pre-send abandonment, network failure, and blob/DB
rollback paths. This requires a minimal observable unit-of-work interface at the
application constructor, not a schema change.

## 4. Retry, budget, timeout, and allowlist ownership

### 4.1 One retry authority

The generic `ProviderRetryPolicy` is shared and currently treats 429 as
transient. It is not a Gate B bug and must not change globally.

The **SEC Gate B execution retry controller** is the only final retry authority.
For this composition, `SafeHttpClient.max_attempts` is fixed to `1`, so the HTTP
client performs exactly one physical attempt and never runs a second hidden
retry loop. The SEC controller classifies 429 as terminal/no-retry and allows at
most one approved transient retry for the whole plan. The generic policy and its
defaults remain unchanged. RED-035 and RED-036 must target this controller rather
than the generic policy.

### 4.2 Separate budget owners

- Resource budget: the immutable three-slice Sync Plan and its checksum;
  `resource_count <= 3`.
- Attempt budget: atomic live-authorization consumption reservations;
  `attempt_count <= 4`.
- Retry budget: the SEC Gate B controller over authoritative persisted attempt
  lineage across the entire Sync Run; `count(attempt_number > 1) <= 1`.

These are separate counters. A retry receives the same approved resource/slice
identity with the next attempt number and consumes a fresh authorization
reservation. A pending reservation after an ambiguous crash blocks continuation
until reconciliation; it cannot be used to manufacture another retry token.

The persisted count is a final invariant, not sufficient pre-send enforcement.
For every retry, the SEC Gate B pilot application owns one atomic operation under
the authoritative authorization/Sync Run lock:

1. acquire the authoritative retry-budget state;
2. revalidate grant, approval, plan, request, attempt, duration, and global retry
   eligibility;
3. reserve the next retry attempt identity and its live-authorization consumption;
4. commit that reservation;
5. only then permit credential resolution, DNS, or `send_start`.

Two concurrent controllers cannot both observe the one retry token as available
and both commit a retry reservation. A retry whose atomic reservation does not
commit must produce no DNS or socket activity. The exact repository method and
lock implementation belong to the later TDD slice; the required observability
is a committed retry reservation event before `send_start` and zero send calls
for the losing concurrent controller.

Accordingly, RED-036 must prove both the persisted global invariant and the
safety boundary: the forbidden second retry cannot reach DNS or `send_start`.

### 4.3 Timeouts

Generic defaults remain 5-second connect, 15-second read, and 30-second total.
The SEC transport policy factory owns the Gate B override: 10-second connect,
30-second idle read, 120-second total run, zero redirects, and one transport
attempt. The immutable approved plan binds these values; the transport is the
final enforcer. RED-037 must call the SEC policy factory rather than construct a
generic default policy.

### 4.4 Host and path scope

The immutable, checksum-bound Gate B plan built from `SEC_ENDPOINT_POLICIES` is
the single source of truth for exact HTTPS method, host, port, and path. The
grant narrows to the same official domains and references the plan checksum.

The SEC request builder proves that the requested endpoint is one of the three
plan resources. Immediately before send, the HTTP client enforces HTTPS, exact
host/port, protected headers, resolved-IP policy, and zero redirects. Host-only
authorization is insufficient. No second mutable path registry is introduced.

## 5. Response, artifact, audit, and stop ownership

- Transport: one physical HTTPS GET and a bounded response envelope. It does not
  create DocumentVersion, Citation, Evidence, Claim, or Report records.
- SEC response validator: endpoint identity, status, MIME, non-empty/size bounds,
  CIK/accession/document identity, temporal rules, and deterministic checksum.
- Provider ingestion application: atomic blob storage, terminal request-attempt
  audit, `ProviderRawArtifact`, Provider Ingestion Manifest, and checkpoint.
- Existing live-evidence/document services: source-neutral manifest,
  DocumentVersion, deterministic parse/chunk, Citation verification, and Data
  Quality.
- SEC pilot application: orchestration, transaction boundaries, retry/budget
  controller, and the explicit `LiveValidationResult` stop at Data Quality.

Audit remains three linked views rather than a new mega-record:

1. request-attempt audit from authorization consumption, Sync Run, plan slice,
   and `ProviderRequestAttempt`;
2. raw-artifact audit from blob identity, checksum, source, policy/license, and
   `ProviderRawArtifact`;
3. ingestion audit from manifests, DocumentVersion, parser/chunker/Citation, and
   Data Quality lineage.

The existing tables contain the required typed identifiers and FKs. The only
required change is the attempt repository's acceptance of the preallocated UUID.
No schema change or migration is required.

### 5.1 Blob/database consistency

`AtomicProviderArtifactStorage` makes the physical blob and its metadata sidecar
durable as one storage entry. It does not make that entry and PostgreSQL one
distributed transaction. The legal failure window is: blob publication succeeds,
the Post-response Settlement Transaction begins, database persistence fails, and
the database transaction rolls back.

A physical blob without committed authoritative database lineage is an
`ORPHAN_BLOB` and is **NON-AUTHORITATIVE**. It is not a validated Raw Artifact,
successful ingestion, Citation source, Evidence source, Claim source, or Report
source. Database rollback must leave no committed `ProviderRawArtifact`, success
manifest/checkpoint, successful attempt/audit state, or downstream promotion for
that failed settlement.

The application must attempt precise compensating deletion only for the exact
new unreferenced blob created by the failed operation. Failure or uncertainty in
that cleanup must preserve the bytes as non-authoritative and report the failure;
it must not claim success. The existing bounded `ProviderArtifactReconciler`
classifies such storage-only entries as `ORPHAN_BLOB`. Reconciliation remains
explicit, checksum-first, and non-mutating by default; garbage collection requires
an explicit deletion policy. An orphan is not automatically adopted or reused as
authoritative data. A later identical ingestion follows normal source-identity and
checksum idempotency and can create or reuse only committed database lineage.

RED-043 and RED-045 must inject database failure after a successful blob write and
prove that settlement rolls back, no authoritative `ProviderRawArtifact` or
successful ingestion/audit state exists, no downstream stage starts, and any
remaining physical blob is reported as a safe non-authoritative orphan eligible
only for explicit reconciliation/garbage collection.

### 5.2 Committed Data Quality STOP

The SEC pilot application owns STOP. A Data Quality STOP is a successfully
committed, audited terminal outcome, not a persistence failure and not a rollback
trigger. The successful path is:

`validated response -> committed Raw Artifact/provenance/ingestion -> Data
Quality evaluation -> committed DQ result and terminal live-validation status ->
STOP`

The artifact, provenance, attempt audit, manifest/ingestion lineage, DQ issues or
pass result, and terminal `ProviderLiveValidationRun` outcome remain retained.
The DQ transaction cannot roll back the already committed valid artifact and
provenance merely because the pilot must stop or because DQ is `PARTIAL`,
`BLOCKED`, or `FAILED`. Only an actual persistence or integrity failure rolls
back its corresponding bounded transaction; prior committed authoritative lineage
remains auditable and cannot be relabeled as pilot success.

After the DQ terminal commit, the application returns an immutable, secret-free
`LiveValidationResult` whose terminal stage is `DATA_QUALITY`. It does not call
Snapshot creation, Research Request, Agent Run, Claim, Report, publication, or
Stage 11 composition. RED-049 must prove both sides: the DQ result and terminal
pilot outcome are persisted/auditable, and no downstream Claim, Report, or Stage
11 composition occurs.

## 6. Considered alternatives

1. Add a persisted `DECLARED_CONTACT_IDENTITY` resolver enum. Rejected: it adds
   a migration and duplicates a role already expressed by
   `user_agent_reference_id`; the existing environment resolver is sufficient.
2. Store the resolved contact string in `HttpClientPolicy`. Rejected: the frozen
   dataclass is printable and would enlarge the leakage surface.
3. Let `SafeHttpClient` and the application both retry. Rejected: two authorities
   can exceed the global attempt budget.
4. Hold one transaction across reservation, HTTP, and ingestion. Rejected: it
   holds locks during an external wait and violates the committed boundary.
5. Delay all persistence until after send. Rejected: it permits concurrent budget
   oversubscription and loses pre-socket idempotent reservation.
6. Treat blob publication as a database commit or introduce distributed 2PC.
   Rejected: storage/database atomicity is enforced through authoritative DB
   lineage, compensation, reconciliation, and idempotency instead.
7. Roll back admitted artifact lineage when Data Quality stops the pilot.
   Rejected: it erases required failure evidence and confuses a terminal safety
   decision with persistence failure.

## 7. Implementation slices

### Step 1B-1 — Production authorization composition

Target REDs: RED-028, RED-029, RED-031, and RED-046.

Scope:

- production authorization input/application and composition factory;
- strict provider/candidate/plan/budget/expiry/single-use validation;
- bind existing credential/user-agent references without resolving values;
- production authorization gate exposed to, but not yet sending through, the SEC
  pilot application.

Allowed production modules:

- `stock_research_agent/cli_live.py`;
- a focused `domain/live_evidence/gate_b_authorization.py` application contract;
- `domain/live_evidence/schemas.py` only for the bounded composition input/result;
- `db/repositories/live_evidence.py` and the existing provider/security query
  repositories only as required to compose committed records;
- one focused production composition module, for example
  `gate_b_live_application.py`.

No HTTP transport, credential resolution, artifact persistence, schema, or
migration belongs in 1B-1.

### Step 1B-2 — SEC transport policy composition

Target REDs: RED-032, RED-034, RED-035, RED-036, RED-037, RED-038, and RED-039.

Scope:

- deterministic three-resource request construction from the approved plan;
- SEC-specific policy factory, exact host/path enforcement, zero redirects,
  timeouts, concurrency/rate settings, and `max_attempts=1`;
- the single SEC retry controller and global retry token;
- execution-time contact resolution and typed redacted request identity;
- fake transport only in tests; no external network.

Allowed production modules:

- `providers/sec_edgar/endpoints.py`;
- focused new `providers/sec_edgar/request_identity.py`, `policy.py`, and
  `transport.py` modules;
- `providers/credentials.py` for the typed protected User-Agent binding;
- `providers/http_client.py` only for accepting/unwrapping the redacted identity
  at final protected-header emission;
- a focused SEC retry controller module; `providers/retry.py` generic defaults
  remain unchanged;
- the SEC pilot application composition surface in `cli_live.py` or its focused
  production application module.

RED-035 through RED-038 require ownership-correct test assertions; their safety
intent remains unchanged. Step 1B-2 defines the retry controller and its atomic
reservation port and can verify ordering/no-send behavior with deterministic
fakes. RED-036 cannot receive its final production GREEN until Step 1B-3 supplies
and concurrency-tests the PostgreSQL-backed atomic reservation implementation.
This is an explicit slice dependency, not permission for an in-memory-only Gate B
retry guarantee.

### Step 1B-3 — Artifact, audit, transaction, and stop boundary

Target REDs: RED-043, RED-044, RED-045, and RED-049.

Scope:

- caller-owned Reservation / Settlement Transaction Model and injectable
  unit-of-work factory;
- preallocated attempt UUID accepted by the attempt repository;
- response validation, atomic blob handling, explicit orphan reconciliation,
  attempt settlement, artifact, manifest, and checkpoint persistence;
- DocumentVersion, parse/chunk, Citation, and Data Quality composition;
- secret-free linked audit view and committed-terminal `LiveValidationResult`
  STOP.

Allowed production modules:

- the focused Gate B/SEC pilot application module and `cli_live.py` factory;
- `domain/providers/sync.py` and `db/repositories/providers.py` only for the
  application-supplied attempt UUID contract;
- `db/repositories/live_evidence.py` for bounded reservation/settlement usage;
- `infrastructure/provider_artifact_storage.py`;
- existing provider artifact/manifest repositories and document bridge;
- `domain/live_evidence/offline_pipeline.py`, `document_bridge.py`,
  `citation_eligibility.py`, and `validation.py` only through their existing
  domain contracts;
- a focused immutable `LiveValidationResult` schema/query composition.

Step 1B-3 requires the documented loopback-only PostgreSQL test configuration to
prove locking, atomic retry reservation, transaction ordering, abandonment,
blob/DB rollback and orphan handling, FK lineage, DQ terminal persistence, audit
persistence, and artifact idempotency. It must not read production database
credentials.

## 8. Entry conditions and preserved boundaries

Implementation is eligible to begin with Step 1B-1 only after human approval of
this design.
Each slice remains offline and TDD-driven. RED-030, RED-033, RED-040, RED-041,
RED-042, RED-047, and RED-048 must remain GREEN throughout.

This design does not authorize Gate B. Exact filing, accession, date, primary
document, request endpoints, as-of, retention, contact reference, grant,
single-use approval, plan checksum, and fresh provider-policy verification remain
future authorization inputs. Gate B readiness remains `NO_GO` after every
enablement slice until those operational and safety conditions are separately
verified and explicitly approved.
