# Stage 10 Controlled Live Evidence Design

Status: `DESIGN READY`

English name: Controlled Live Validation, Governed Evidence Onboarding and
Real-Company Research Pipeline

This document is a design gate. It does not authorize implementation, a Live
request, credential resolution, a real-file import, Snapshot creation, Agent
execution, report generation, or Stage 11 work.

## 1. Background and verified baseline

The design was prepared on `main` at `d6368d5`. Stage 9 entered `main` through
the squash commit `839f0d6`; `d6368d5` preserves the exact blocked-provider
reason contracts. The verified baseline is:

- PostgreSQL 17.10 development database `stock_research` and test database
  `stock_research_test` are distinct loopback databases;
- Alembic is `0008_production_providers (head)`;
- all 20 Stage 9 Provider tables exist in both databases;
- Ruff, the 539-file format check and strict mypy over 248 source files pass;
- default pytest is fully offline and reports `2537 passed`, zero failed,
  errors, skipped and warnings in 398.58 seconds;
- no Provider credential was read, no Live request was attempted, and no
  Snapshot, Agent Run or Report was created by this design work.

The current Security Master deterministically resolves:

- `MU` to security `40000000-0000-0000-0000-000000000002`, issuer
  `30000000-0000-0000-0000-000000000002`, exchange `XNAS`; its persisted
  `SEC_CIK` is `0000723125`;
- `601138.SH` to security `40000000-0000-0000-0000-000000000001`, issuer
  `30000000-0000-0000-0000-000000000001`, exchange `XSHG`.

Both securities currently have listing status `UNKNOWN`. That warning remains
visible and is not converted to `ACTIVE` by the Live or manual workflows.

## 2. Problem definition

Stage 9 proves an offline Provider control plane. It does not prove that a real
response may be acquired, retained, parsed and admitted as company evidence.
Stage 10 must connect authorized source acquisition to immutable evidence and
then, through separate explicit gates, to a new Snapshot, Stage 7 controlled
Research Agent Run and Stage 8 report version. It must do so without treating
public accessibility as a license, metadata as body evidence, manual input as
Provider Live data, or fixture/synthetic content as real-company evidence.

## 3. Success criteria

The future implementation is successful only when it can:

1. represent a finite, immutable, revocable Live authorization;
2. meter every actual HTTP attempt and byte against that authorization;
3. safely quarantine and review a user-supplied official file without network;
4. preserve exact original bytes and immutable manifests for both intake paths;
5. admit only license-approved, identity-matched, non-future, non-synthetic
   evidence;
6. explicitly create a new immutable Snapshot without changing an old one;
7. explicitly run the existing offline/read-only controlled Agent;
8. explicitly create a new versioned report and let the existing Release Gate
   determine its result;
9. preserve complete lineage and deterministic checksums; and
10. stop safely on authorization, license, credential, security, quality or
    temporal failure.

The design itself is accepted as `DESIGN READY`, not `GO`, `Live PASS`,
`PRODUCTION_READY`, or `PRODUCTION_ACTIVE`.

## 4. Route comparison

| Route | Scope | Strength | Material weakness | Decision |
|---|---|---|---|---|
| A | SEC, Tushare, A-share bodies, U.S. EOD and Embedding together | Broad coverage | Rights, credentials and transport readiness are unresolved; failures cannot be isolated | Rejected |
| B | SEC limited Live only | Small, auditable trial | Leaves Industrial FII without a compliant evidence path and does not test manual onboarding | Acceptable fallback |
| C | One finite SEC pilot plus controlled manual A-share evidence import | Tests both official Live and user-supplied evidence while retaining one governance path | Requires a strict file quarantine/review subsystem and two separate user approvals | Recommended |

### Route A: multiple Live Providers together

Rejected because unresolved licenses, credentials and endpoint contracts would
expand several independent risks at once.

### Route B: SEC limited Live only

Accepted only as a fallback because it is narrow and auditable but leaves the
A-share evidence path untested.

### Route C: SEC limited Live plus controlled manual A-share import

Recommended because it tests both source mechanisms without authorizing blocked
A-share automation or any other Provider.

Route C is recommended because it is the smallest route that tests both sample
markets without bypassing blocked A-share automation. This recommendation is not
approval. Implementation still requires the exact phrase `批准第10阶段设计并继续实现`.
The SEC execution later requires the separate exact phrase
`批准执行该SEC有限Live验证`. A real manual file requires the user to supply the
file and explicitly approve that specific import.

## 5. Stage boundary and two implementation gates

### Gate A: offline engineering

After design approval, Gate A may add versioned models, migration, repository and
domain services, a local-only manual intake Provider definition, Fake Transport,
safe fixtures, CLI, GET-only API, tests and documentation. Gate A remains
`OFFLINE`, `NOT_LIVE` and `NOT_ATTEMPTED`; it may not resolve a real Provider
credential, import a real company file, create a real-company Snapshot, or write
Live data.

### Gate B: finite Live execution

Gate B can start only after Gate A passes all default tests and a concrete SEC
plan is disclosed and separately approved. It is limited to one Provider, one
capability set, one security, one CIK, one filing form and accession, three
planned resources, one primary document and finite time/byte/request budgets.
Gate B does not authorize Tushare, A-share automation, U.S. EOD, Embedding or a
model.

## 6. Fixed governance order

Every automated acquisition uses the Stage 9 fail-closed order:

`Definition -> Capability -> License -> Provider Policy -> Credential Reference
-> Configuration Validation -> Live Authorization Grant -> Execution Approval
-> Rate Limit -> Circuit Breaker -> Remaining Budget -> HTTP`.

Failure at one gate prevents construction or invocation of every later network
component. Manual import replaces the network gates with:

`Local Intake Definition -> Source Declaration -> License Declaration -> Root-safe
File Resolution -> Quarantine -> Content Validation -> Human Review -> Manifest`.

Neither path can write a Claim, Research Package, Report, Derived Metric or Agent
output directly.

## 7. LiveAuthorizationGrant

`LiveAuthorizationGrant` is an immutable scope record. Lifecycle is represented
by append-only events; the base row is never edited. The derived states are
`DRAFT`, `APPROVED`, `ACTIVE`, `CONSUMED`, `EXPIRED`, `REVOKED` and `CANCELLED`.
Terminal states cannot reactivate. Enlarging any field creates a new grant.

The frozen fields are:

- `authorization_id`, `provider_definition_id`, `provider_code` and exact
  definition version;
- `provider_capability_id`, `capability_code` and exact capability version;
- `security_id`, issuer identity and normalized Provider security identifier;
- sorted exact `official_domains`, exact HTTPS methods and concrete request paths;
- exact filing form, accession, date window and `allowed_document_count`;
- `request_limit`, `byte_limit`, total retry budget and duration limit;
- `credential_reference_id` and `user_agent_reference_id`, never their values;
- Provider policy, endpoint policy and license policy IDs/versions/checksums;
- raw-storage, cache, excerpt, derived-use and redistribution decisions;
- retention deadline, approved/expiry times, approving actor and canonical
  checksum.

The canonical checksum excludes database-generated IDs and timestamps that do
not define scope. It includes every field that can change network reach, evidence
rights or downstream eligibility.

## 8. Authorization lifecycle and concurrency

An append-only `live_authorization_event` derives the current state. Activation
requires an immutable `LiveExecutionApproval` whose checksum binds the grant and
the exact Sync Plan. Every actual HTTP attempt first inserts a
`live_authorization_consumption` under a PostgreSQL row/advisory lock, checking
remaining request, byte and duration budgets atomically. Reservations are
settled with actual bytes; failed attempts still consume request and received
byte budgets. Idempotency is `(authorization_id, request_attempt_id)`.

Revocation wins over an unstarted request. A request already streaming checks the
revocation/cancel token between chunks and stops without persisting a completed
artifact. No retry can cross expiry or reset consumption. Crash recovery may
release an unstarted reservation only when the audit proves no socket was opened;
otherwise it remains consumed.

## 9. Candidate SEC pilot

The candidate pilot uses the existing `SEC_EDGAR_PUBLIC_V1` definition and only
the exact hosts already registered in Stage 9:

- `data.sec.gov` for one submissions metadata resource;
- `www.sec.gov` for one filing index resource and one primary filing document.

The Security Master supplies CIK `0000723125`; the operator cannot override it.
The selected form is exactly one of `10-K` or `10-Q`; the accession and primary
document name come from the validated submissions record and are frozen before
approval. The first pilot excludes Company Facts, exhibits, complete-submission
archives, historical backfill and third-party mirrors.

Candidate hard limits, subject to an equal-or-smaller separately approved plan:

- three planned resources and at most four actual HTTP attempts;
- at most one retry across the whole plan, only for an approved transient error;
- 25 MiB total received bytes, including failed response bodies;
- 2 MiB submissions limit, 1 MiB index limit and 20 MiB primary-document limit;
- one concurrent request and no more than one request per second;
- 10-second connect timeout, 30-second idle read timeout and 120-second total run;
- zero redirects; exact HTTPS host/path validation on every request;
- one primary document and zero exhibits;
- grant expiry no later than 30 minutes after activation;
- execution approval expiry no later than 10 minutes after confirmation;
- cache disabled; raw storage required; default evidence retention 30 days unless
  a shorter approved policy applies.

The official SEC access, identification, rate and reuse rules must be re-reviewed
from the official sources immediately before Gate B. The stored Stage 9 review is
design evidence, not a permanent rate or license entitlement. Any changed or
unclear rule blocks activation.

## 10. SEC identity and User-Agent boundary

The pilot binds a `ProviderCredentialReference` of resolver kind
`DECLARED_CONTACT_IDENTITY` to the grant. Only its safe name, status and version
are persisted. The actual contact/User-Agent value may be resolved inside the
authorized transport only after all preceding gates pass. It is never returned,
hashed, prefixed, suffixed or logged. SEC needs no API token; an absent or invalid
contact identity blocks the run before DNS or socket creation.

## 11. SEC execution sequence

The future run performs, without automatic continuation:

1. resolve `MU`, issuer and CIK from persisted Security Master records;
2. freeze Provider, Capability, Policy and License versions;
3. build and display the three-resource plan and all budgets;
4. create/activate the finite grant and bind one execution approval;
5. acquire submissions metadata, validate CIK/form/accession and as-of;
6. acquire the exact filing index, validate primary-document identity;
7. acquire the exact primary document, stream bounds and checksum it;
8. persist Request Attempt audit, immutable Raw Artifact and Ingestion Manifest;
9. parse metadata/index/body offline into a new DocumentVersion;
10. parse/chunk and create Citation candidates, then run deterministic Citation
    verification;
11. write Data Quality results and stop.

It does not automatically create a Snapshot, run the Agent or generate a Report.

## 12. SEC validation status

`LIVE_VALIDATION_PASS`, `LIMITED_PRODUCTION_PILOT`, `PRODUCTION_READY` and
`PRODUCTION_ACTIVE` remain separate. One successful filing can establish only
`LIVE_VALIDATION_PASS`. It cannot establish all-form coverage, production SLA,
historical backfill safety, current financial completeness, market-price data,
or complete Micron research.

## 13. ControlledManualEvidenceImport

Manual evidence uses a local-only governance definition
`CONTROLLED_MANUAL_EVIDENCE_V1`. It is always `NOT_LIVE`, `requires_network=false`
and cannot accept a URL as a fetch target. It creates a normal Stage 4
`IngestionRun` for the local-only `DataProvider`, then writes the exact bytes to
the source-neutral `raw_payloads` contract without fabricating an HTTP request.
A new source-neutral `evidence_ingestion_manifests` row binds that payload to the
source declaration, validations and review. Presentation must say `USER_SUPPLIED`
or `MANUAL_IMPORT`, never `Provider Live`.

Source types are:

- `USER_SUPPLIED_OFFICIAL_DOCUMENT`;
- `USER_SUPPLIED_PROVIDER_EXPORT`;
- `USER_SUPPLIED_STRUCTURED_DATA`;
- `USER_SUPPLIED_UNVERIFIED_DOCUMENT`.

Only the first three may become real-company evidence, and only after identity,
source, rights, content and human-review gates pass. Unverified material remains
quarantined and can explain a limitation only.

## 14. Manual import request and derived states

The immutable request freezes security/issuer IDs, an opaque submitted-file
reference, sanitized original filename, declared source and URL/description,
document type, report period, publication/retrieval time, language, acquisition
method, license/commercial-use declarations, raw-storage/excerpt/long-term-use
decisions, submitted actor, synthetic status and checksum.

The base row starts as `RECEIVED`. `QUARANTINED`, `VALIDATING`, `APPROVED`,
`PARTIAL`, `REJECTED`, `BLOCKED` and `INGESTED` are derived from append-only
validation, review and manifest rows. A later correction is a new request and
new bytes; it never changes a prior request or DocumentVersion.

## 15. Manual file security

Initial accepted formats are PDF, HTML and JSON only. The CLI accepts a path
relative to a configured manual inbox root; absolute paths, traversal, UNC paths,
Windows device names, alternate data streams, hidden/double extensions, symlink
escape and case/Unicode-confusable extension tricks are rejected. The absolute
source path is never persisted or returned.

The default limit is one file and 25 MiB per request. ZIP, gzip, RAR, 7z, XML,
SVG, executable formats and nested containers are rejected. Validation compares
extension, declared MIME, detected MIME and magic bytes. PDF inspection rejects
encryption, JavaScript, Launch/OpenAction, embedded files and suspicious object
counts. HTML is parsed as inert bytes; scripts, event handlers, forms, iframes,
external resources, data URLs and local-file references block admission. JSON is
UTF-8, at most 32 levels and 100,000 nodes, with no non-finite numbers or duplicate
keys. No parser executes code, follows a link, loads a resource, invokes OCR or
uses a macro.

Quarantine storage uses an atomic UUID-based blob key under a dedicated root,
read-only parsing workers, bounded memory/time and no network. Failure leaves the
file quarantined or deletes uncommitted temporary bytes according to the source
declaration; it never promotes the file.

## 16. Manual source and evidence validation

Admission requires exact Security and Issuer match, document type, period and
publication date consistency, complete source explanation, checksum, non-future
publication, explicit license decisions, `REAL_VERIFIED` synthetic status and a
human approval bound to the validation checksum. An official URL is descriptive
only; the importer never fetches it. A screenshot, chat transcript, secondary
repost or unverifiable file cannot be promoted as official company body evidence.

The full policy is in `docs/manual-evidence-import-policy.md`.

## 17. Unified raw artifact contract

The source-neutral Raw Artifact abstraction is backed by existing immutable
`raw_payloads`. Migration 0009 must add nullable
`manual_evidence_import_request_id`, make `provider_request_log_id` nullable and
add a CHECK requiring exactly one of those two source references. Existing rows
all remain on the Provider-request arm. Manual rows use the manual-request arm,
the local-only `DataProvider` and a real `IngestionRun`; they never invent a
`provider_request_log`. Both paths preserve original bytes before normalization.
Each artifact freezes:

- source mechanism and exact source identity;
- security, issuer, Provider/capability or manual request lineage;
- request attempt or local intake event;
- SHA-256, byte count, MIME and opaque root-safe blob key;
- acquired/retrieved and source-published times without substitution;
- synthetic status and exact license policy decision;
- retention deadline and deletion state.

Cache is never evidence. A parsed or normalized value never overwrites raw bytes.

## 18. Ingestion Manifest

The new source-neutral immutable `evidence_ingestion_manifests` binds one
`raw_payloads` row, acquisition kind, adapter/parser/sanitizer/schema versions,
batch checksum, record count, temporal fields, warning codes, synthetic status,
license decision and canonical checksum. A CHECK requires exactly one upstream:
an existing Stage 9 `provider_ingestion_manifests` row or an approved manual
import request/review. Provider-specific manifests remain unchanged and are
linked, not copied or rewritten. Both paths expose one downstream domain
interface while retaining their distinct acquisition kinds. Replay with the same
canonical inputs reuses the same manifest; changed bytes or policy create a new
version.

## 19. DocumentVersion and Citation

A company body becomes a `DocumentVersion` only after the manifest is admitted.
It uses the existing logical-document identity, exact byte checksum, security,
source payload/artifact and immutable version chain. A correction or withdrawal
creates a new version/event; it never edits an old version, Snapshot, Citation,
Retrieval Run, Agent Run or Report. Citation always binds a concrete
DocumentVersion and must pass the existing deterministic verifier before it may
support a Claim.

Metadata, filing index rows and blocked/manual-unverified records cannot masquerade
as body Citation evidence.

## 20. Explicit Snapshot creation

`CreateSnapshotFromIngestion` is a plan-then-create workflow. The plan freezes one
Security, admitted Provider/manual manifests, DocumentVersion IDs, raw financial
fact IDs, Provider and concept mapping versions, Formula Registry version,
`research_as_of_time`, publication cutoff, Data Quality result, license policy
versions, synthetic status and canonical checksum. Credential references and
values are excluded.

Creation rejects future or unknown strict-publication evidence, other securities,
other unapproved runs, synthetic company data, unapproved manual files, blocked
evidence and unknown body sources. It creates a new immutable `data_snapshots` row,
`snapshot_items`, `snapshot_document_versions` and immutable
`ingestion_to_snapshot_bindings`. It never updates an old Snapshot and does not
run the Agent.

## 21. Explicit Research Agent Run

`research run-from-snapshot` invokes the existing Stage 7 controlled Agent only
after a new Snapshot is sealed. Tools remain `READ_ONLY`, `writes=false` and
`requires_network=false`. The Agent reads persisted evidence only, does not resolve
credentials, refresh a Provider, change the Snapshot, expand security/as-of scope,
or call a model. Its DAG and budgets remain finite. Evidence gaps yield `PARTIAL`
or `BLOCKED` and are not filled by synthetic content.

## 22. Explicit Report generation

`report generate-from-package` invokes the existing Stage 8 pipeline only after a
sealed Research Package exists:

`Research Package -> ReportInputManifest -> canonical JSON -> deterministic
Markdown -> Reflection 1 -> at most one Revision -> Reflection 2 -> Release Gate`.

It creates a new report version and preserves all earlier reports. The existing
Release Gate alone decides `PUBLISHABLE`; the command cannot force that state.
Claims, evidence, Citations, manifests, checksums, quality warnings and limitations
remain traceable.

## 23. Industrial FII boundary

Industrial FII automatic disclosure acquisition remains `BLOCKED`. A user may
later supply one legally obtained official report under a separately approved
manual request. If admitted, Claims must be limited to that document's stated
period/as-of and the resulting package/report remains at most `PARTIAL` unless all
existing evidence gates independently pass. The system cannot claim latest price,
latest quarter, real-time valuation, target price, rating, advice, missing
announcements or industry facts.

## 24. Micron boundary

The SEC pilot is limited to one selected 10-K or 10-Q primary document. Filing
metadata remains metadata. Company Facts is not included in the first pilot, so
structured facts remain `NOT_REQUESTED` or `BLOCKED`; they are not inferred from
body text. One filing may support cited historical Claims and a `PARTIAL` report,
but not real-time price, an unimported quarter, current HBM demand, inventory-cycle
conclusions, target price, rating or trading advice.

## 25. License boundary

Every requested use is separately evaluated for acquisition, raw storage, cache,
derived use, excerpt, redistribution, retention and deletion. `UNKNOWN`, expired,
inconsistent or prohibited rights fail closed. Route C does not change Tushare's
`RESTRICTED_REVIEW_REQUIRED/BLOCKED` state, A-share automation's blocked state,
the unselected U.S. EOD Provider or production Embedding. A single SEC validation
does not grant production or redistribution rights.

## 26. Credential boundary

The database stores only an immutable reference and safe status. No secret,
contact value, token, cookie, Authorization header, value hash, prefix or suffix
may enter a model, migration, log, test, API, Tool, report or checksum. Merely
finding an environment variable never enables a Provider. Credential/contact
resolution occurs only inside an ACTIVE, unexpired, exact-scope Gate B transport
after every earlier gate succeeds.

## 27. Data retention and deletion

Retention is the minimum of the grant, license policy and source declaration.
Deletion uses append-only `evidence_retention_action` records. When rights require
deletion, raw bytes and all cache copies are removed; audit metadata permitted by
policy retains only opaque IDs, checksum, size, dates and deletion evidence.
Affected Snapshots/reports are marked through new validation/incident records as
no longer fully reproducible; their historical rows are not silently edited.

No deleted restricted content may survive in logs, fixtures, temporary files or
backups governed by this application. Physical backup handling is an operator
precondition recorded in the deletion action.

## 28. Business rollback

Business correction is append-only: new Artifact, Manifest, DocumentVersion,
Snapshot, Agent Run and Report. A bad Live pilot stops its Sync Run, revokes or
consumes the grant, opens the scoped circuit when appropriate, removes uncommitted
temporary bytes, retains safe audit, does not advance the checkpoint and creates
no downstream object. A bad manual import remains quarantined/rejected.

Database downgrade is permitted only before any retained Stage 10 evidence exists,
or after an explicit export/deletion review proves the downgrade will not orphan
regulated bytes or audit. Historical Stage 2-9 tables are never dropped by the
Stage 10 downgrade.

## 29. Incident handling

`live_incident` plus append-only `live_incident_event` covers credential exposure,
rate violations, blocking, excessive download, host mismatch, SSRF, corrupt bytes,
checksum conflict, license/terms change, future data, wrong Security, forged manual
source, malicious file, wrong Snapshot, Agent evidence misuse and broken report
Citation. Each incident has detection code, severity, automatic stop action,
quarantined lineage, remediation, downstream impact, user-approval requirement and
closure evidence. The operational matrix is in the runbook.

## 30. Database design

Stage 10 evaluates and recommends these new tables:

| Table | Purpose and invariants |
|---|---|
| `live_authorization_grants` | Immutable finite scope; unique canonical checksum; RESTRICT to Provider, Capability, Security, policy and credential reference |
| `live_authorization_events` | Append-only lifecycle; unique grant sequence; legal transition CHECK/service parity |
| `live_authorization_consumptions` | Append-only request/byte meter; unique request attempt; atomic budget reservation/settlement |
| `live_execution_approvals` | Immutable single-use approval binding grant and plan checksums |
| `manual_evidence_import_requests` | Immutable intake identity and safe file metadata |
| `manual_evidence_source_declarations` | Immutable source/license/use declaration; one version per request |
| `manual_evidence_validations` | Append-only bounded validator result and checksums |
| `manual_evidence_reviews` | Append-only human/system decisions; no raw content |
| `evidence_ingestion_manifests` | Source-neutral immutable manifest over one RawPayload and exactly one Provider/manual upstream |
| `ingestion_to_snapshot_bindings` | Immutable manifest/document/fact-set to new Snapshot lineage |
| `real_company_validation_runs` | One finite real-company validation aggregate with terminal status |
| `end_to_end_research_validations` | One row per deterministic validation check and evidence reference |
| `evidence_retention_actions` | Append-only retention/deletion audit without retained body |
| `live_incidents` | Immutable incident identity and frozen affected scope |
| `live_incident_events` | Append-only detection, containment, remediation and closure events |

The minimum key/constraint/index contract is:

| Table | Key constraints and indexes | State/concurrency/delete rule |
|---|---|---|
| `live_authorization_grants` | unique `canonical_checksum`; FKs to exact Provider/Capability/Security/policy/license/credential reference; CHECK positive finite limits, ordered dates, HTTPS GET scope and one document | immutable trigger; state derived from events; RESTRICT delete |
| `live_authorization_events` | unique `(authorization_id, sequence)` and `event_checksum`; index `(authorization_id, sequence desc)` | append-only; legal transition validated against prior event under grant lock |
| `live_authorization_consumptions` | unique `(authorization_id, request_attempt_id)`; CHECK nonnegative reserved/actual bytes and attempts; index by grant/time | append-only settlement record; budget reservation under grant lock; RESTRICT delete |
| `live_execution_approvals` | unique approval and canonical checksums; FKs to grant and exact sync plan; CHECK approval/expiry order | immutable and single-use; consumption derives use; RESTRICT delete |
| `manual_evidence_import_requests` | unique request checksum; FKs Security/Issuer; CHECK bounded filename/size/source type/synthetic state; index Security/time | immutable; derived state; RESTRICT delete |
| `manual_evidence_source_declarations` | unique `(import_request_id, declaration_version)` and checksum; typed rights CHECKs | immutable; replacement appends version/new request; RESTRICT delete |
| `manual_evidence_validations` | unique `(import_request_id, validator_code, validator_version, input_checksum)`; status/severity CHECK; index request/time | append-only; validators cannot overwrite results |
| `manual_evidence_reviews` | unique review checksum; FKs request/declaration/validator-set; decision CHECK; index request/time | append-only; blocking checks cannot be waived |
| `evidence_ingestion_manifests` | unique canonical checksum; FK RawPayload; exactly one Provider Manifest or manual request/review arm; acquisition/synthetic/license CHECKs | immutable trigger; created with admitted source records; RESTRICT delete |
| `ingestion_to_snapshot_bindings` | unique `(snapshot_id, ingestion_manifest_id)` and binding checksum; FKs Snapshot/Manifest/DocumentVersion as applicable; Security consistency CHECK | immutable trigger; created in Snapshot transaction; RESTRICT delete |
| `real_company_validation_runs` | unique input/idempotency checksum; FKs Security/Snapshot/Agent Run/Package/Report as present; terminal-status CHECK; index Security/time | mutable only through legal finite states, immutable at terminal |
| `end_to_end_research_validations` | unique `(validation_run_id, check_code, check_version)`; status CHECK; bounded evidence reference | append-only checks; no JSON-only audit |
| `evidence_retention_actions` | unique action checksum; FK to exact Artifact/Manifest and incident; action/result CHECK; index deadline/status | append-only; physical deletion is idempotent and separately verified |
| `live_incidents` | unique incident checksum; typed category/severity and affected Provider/Security/run/artifact FKs; index open scope/time | immutable identity; current state derived from events; RESTRICT delete |
| `live_incident_events` | unique `(incident_id, sequence)` and checksum; event/status CHECK | append-only under incident lock; closure terminal |

Where one business concept may reference either Provider or manual lineage, the
schema uses explicit nullable FKs plus a CHECK requiring exactly one source kind;
it never stores an unauditable arbitrary source ID in JSON.

Existing `provider_live_validation_runs` remains the Provider execution outcome;
it references the new grant and does not replace it. Existing Raw Artifact,
Manifest, DocumentVersion, Snapshot, Agent and Report tables remain authoritative.

Migration 0009 also evolves `raw_payloads` with the exactly-one source-reference
CHECK described in section 17. It does not update an existing RawPayload or relax
its checksum/storage/immutability constraints. Existing Provider manifests feed
the source-neutral manifest through an explicit FK; no historical Provider row is
rewritten. Because the candidate primary-document and manual-file bounds can exceed
the current 10,000,000-byte `document_versions` CHECK, 0009 replaces that CHECK
with an upper bound of 26,214,400 bytes after a focused migration test. Existing
DocumentVersion rows and checksums are untouched; the application continues to
enforce the lower per-resource limits from the grant/import plan.

All new tables use UUID primary keys, UTC timestamps, named FK/UNIQUE/CHECK
constraints, bounded strings, explicit indexes for grant status lookup,
consumption totals, import state, security/time and incident scope, and RESTRICT
deletes. JSONB is allowed only for bounded frozen allowlists/reason lists; core
authorization, rights, identity, status and lineage remain typed columns. Terminal
records use PostgreSQL immutability triggers. Downgrade removes only Stage 10
objects and must fail safely when retained Stage 10 lineage would be orphaned.

## 31. Transaction and concurrency model

Grant activation, consumption and revocation use `SELECT FOR UPDATE` or a stable
advisory-lock key per authorization. Artifact bytes are atomically written before
the DB transaction records the final blob key; failed DB commits remove only the
new unreferenced temporary object. Manifest admission and source records commit in
one caller-owned transaction. Snapshot creation locks the plan checksum and
acquires immutable items in one transaction. Idempotency keys cover grant/event,
manual request/bytes, manifest, Snapshot, Agent Run and Report input.

### 31.1 Domain interface contracts

Gate A must implement these versioned, transaction-neutral ports; API and CLI
adapters may not duplicate their rules:

```python
class LiveAuthorizationService(Protocol):
    def plan(self, request: LiveAuthorizationPlanRequest) -> LiveAuthorizationPlan: ...
    def activate(self, request: ActivateLiveAuthorizationRequest) -> LiveAuthorizationRecord: ...
    def revoke(self, request: RevokeLiveAuthorizationRequest) -> LiveAuthorizationRecord: ...
    def reserve(self, request: ReserveLiveConsumptionRequest) -> LiveConsumptionReservation: ...
    def settle(self, request: SettleLiveConsumptionRequest) -> LiveConsumptionRecord: ...

class SecLivePilotService(Protocol):
    def validate(self, request: SecLiveValidationRequest) -> SecLiveValidationPlan: ...
    def execute(self, request: ExecuteSecLivePilotRequest) -> SecLivePilotResult: ...

class ManualEvidenceImportService(Protocol):
    def plan(self, request: ManualImportPlanRequest) -> ManualImportPlan: ...
    def quarantine(self, request: QuarantineManualEvidenceRequest) -> ManualImportRecord: ...
    def validate(self, request: ValidateManualEvidenceRequest) -> ManualValidationResult: ...
    def review(self, request: ReviewManualEvidenceRequest) -> ManualReviewRecord: ...
    def ingest(self, request: IngestManualEvidenceRequest) -> EvidenceIngestionResult: ...

class SnapshotFromIngestionService(Protocol):
    def plan(self, request: SnapshotFromIngestionPlanRequest) -> SnapshotCreationPlan: ...
    def create(self, request: CreateSnapshotFromIngestionRequest) -> SnapshotBuildResult: ...

class RealCompanyValidationService(Protocol):
    def validate(self, request: RealCompanyValidationRequest) -> RealCompanyValidationResult: ...
```

Every request above is an immutable Pydantic model with explicit UUIDs, exact
versions/checksums, aware UTC time, bounded collections and no arbitrary URL,
SQL, local absolute path, credential value, Provider class or model identifier.
Every result exposes stable status/reason/warning codes and safe lineage IDs.
Repository ports accept a caller-owned SQLAlchemy Session and never create one or
perform network/file I/O.

## 32. CLI design

All writes are explicit and separated:

```text
stock-research live authorization-plan
stock-research live authorization-show
stock-research live authorization-activate
stock-research live authorization-revoke
stock-research live sec plan
stock-research live sec validate
stock-research live sec run
stock-research live sec show
stock-research evidence import-plan
stock-research evidence import
stock-research evidence validate
stock-research evidence approve
stock-research evidence reject
stock-research evidence show
stock-research snapshot plan-from-ingestion
stock-research snapshot create-from-ingestion
stock-research research run-from-snapshot
stock-research report generate-from-package
stock-research validation show
```

Plan/show/validate never execute a network request. `live sec run` requires an
ACTIVE grant plus matching, unexpired execution approval. No command chains Live,
Snapshot, Agent and Report. Every command requires exact IDs/checksums rather than
"latest" and accepts no arbitrary URL, host, SQL, Provider class, model or local
path outside the manual inbox contract.

## 33. GET-only API

Under the existing `/api/v1` prefix, the future API may expose bounded GET routes
for authorization summary, SEC plan/run status, manual import/validation summary,
manifest summary, Snapshot readiness, real-company validation and end-to-end
status. Responses omit contact identity, credential references that reveal
resolver names, local paths, blob keys, raw restricted bytes and SQL details.

No POST, PUT, PATCH, DELETE, upload, Live execution, Snapshot creation, Agent run
or report generation endpoint is authorized. The API cannot cause parsing,
indexing, calculation, credential resolution, network or a write.

The bounded route set is:

```text
GET /api/v1/live-authorizations/{authorization_id}
GET /api/v1/live-authorizations/{authorization_id}/consumptions
GET /api/v1/live/sec/plans/{plan_id}
GET /api/v1/live/sec/runs/{run_id}
GET /api/v1/evidence-imports/{import_id}
GET /api/v1/evidence-imports/{import_id}/validations
GET /api/v1/ingestion-manifests/{manifest_id}
GET /api/v1/snapshot-readiness/{plan_id}
GET /api/v1/real-company-validations/{validation_run_id}
GET /api/v1/end-to-end-validations/{validation_run_id}/checks
```

Collection endpoints use a hard `limit` of 1-100, validated identifiers and
stable order; they accept no arbitrary sort or filter expression.

## 34. Test strategy and default offline rule

Gate A follows TDD and PostgreSQL integration testing. Default
`uv run pytest -W error` blocks DNS and real sockets, does not read credentials,
does not collect `tests_live`, and must finish with zero failures, errors, skips
and warnings. It covers authorization scope/replay/expiry/revocation/concurrency,
byte/request limits, SSRF/redirect/host changes, secret redaction, manual path and
content attacks, identity/period/future checks, immutable lineage, deletion,
Snapshot/Agent/Report separation and historical regression.

Safe fixtures are minimal and manifest-backed. Synthetic fixtures are marked
`SYNTHETIC_TEST_ONLY`, `NOT_COMPANY_EVIDENCE`, `OFFLINE`, `NOT_LIVE`; any safe
official crop records source, license, crop rule, checksum and LF byte policy.

`tests_live` is excluded from default pytest/CI. Without a valid grant and exact
execution approval it reports an external run status of `NOT_ATTEMPTED` or
`BLOCKED`; it does not use pytest skip to claim success.

## 35. Risks and unresolved decisions

The following are deliberately unresolved and block Gate B, not design:

- the exact MU filing form, accession, report period and primary filename;
- current official SEC access/User-Agent/rate/reuse rules at execution time;
- the safe configured contact identity reference status;
- the final SEC raw-retention and excerpt decision after current policy review;
- whether the user will approve the disclosed finite SEC plan;
- whether the user will provide a legally obtained Industrial FII official file;
- that file's source, rights, publication date, content safety and review result;
- whether partial real evidence is sufficient for a non-publishable report.

These values cannot be guessed or represented by placeholders. The future plan
must stop until they are concrete and approved.

## 36. Stage conclusion rule and Stage 11 boundary

Stage 10 may later be `GO` only if offline engineering, finite Live authorization,
SEC validation, artifact/manifest, new Snapshot, new Agent Run, new Report,
Citation lineage and all security/license gates pass with zero unresolved CRITICAL
or HIGH findings. Partial evidence or still-blocked Providers yields
`CONDITIONAL GO`. Unauthorized Live, license conflict, credential leak, SSRF,
malicious execution, future/synthetic contamination or history mutation yields
`NO-GO`.

Stage 11 scope is undefined. This design does not authorize public release,
models, MCP, frontend, advice, target price, brokerage, trading or any Stage 11
work.

## 37. Design self-check declaration

The companion documents and this design are subject to the 20-item self-check in
`docs/real-company-research-runbook.md`. At design completion:

- no Stage 10 branch, migration, dependency or production code exists;
- no Credential was read and no DNS, socket or external request was made;
- no real file was imported;
- no Snapshot, Agent Run or Report was created;
- no Stage 11 work was performed.
