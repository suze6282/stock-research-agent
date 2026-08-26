# Stage 10 Gate B Preparation

Status: **NO-GO**

Prepared from committed repository state at `ee71f9b659dd1a10e25df926f6ea735252ac46a8`.

Gate A status: **COMPLETE**
Gate B readiness: **NO_GO**
Gate B authorization: **NOT GRANTED**
Gate B execution: **NOT ATTEMPTED**

## Purpose and scope

Gate B is the finite, controlled validation of one SEC EDGAR live evidence path after Gate A. It is not a complete live research run, provider rollout, model workflow, publication step, Stage 11 entry, or authorization to widen provider scope.

The formal Gate B command stops after raw acquisition, deterministic ingestion, parse/chunk, citation verification, and Data Quality. It does not automatically create a research Snapshot, Agent Run, Evidence, Claim, Package, Report, Reflection, or Release Gate result. Any later offline research workflow requires a separate explicit command and authorization.

Gate A is formally complete. Gate B is currently NO-GO because the committed production composition intentionally has no configured SEC live transport/application, and the exact candidate plan, current provider-policy review, declared contact identity, storage/retention decision, finite authorization grant, and single-use execution approval are not closed.

## Approved candidate envelope

| Field | Approved value |
|---|---|
| Provider | `SEC_EDGAR_PUBLIC_V1` |
| Security | Micron Technology, Inc. (`MU`) |
| Security ID | `40000000-0000-0000-0000-000000000002` |
| Issuer ID | `30000000-0000-0000-0000-000000000002` |
| Exchange | `XNAS` |
| Provider identifier | CIK `0000723125`, resolved from persisted Security Master `SEC_CIK` |
| Document target | Exactly one 10-K or 10-Q |
| As-of behavior | Filed/published/available time must be no later than the approved research as-of time; retrieval time is metadata only |

The provider/security candidate is unique, but the exact form, accession, report period, filing date, index filename, and primary-document filename remain unselected. An operator may not override the persisted CIK or supply an arbitrary URL.

## Network envelope and request budget

Only HTTPS `GET` is allowed. The hostname allowlist is exactly:

- `data.sec.gov`
- `www.sec.gov`

All other hosts, mirrors, third-party services, user-provided URLs, IP literals, redirects, exhibits, complete-submission files, filing history crawls, and Company Facts are outside the Gate B grant.

The planned resources are:

1. `data.sec.gov/submissions/CIK0000723125.json`, for exact filing discovery and identity/as-of validation.
2. The exact SEC filing index under the approved accession, for primary-document identity validation.
3. The exact primary filing document under that accession, for the controlled raw artifact.

Budget and transport policy:

- Planned resources: 3.
- Maximum actual attempts: 4 across the entire plan.
- Retry: at most one retry across the entire plan, only for a pre-approved transient condition while all time, byte, rate, and authorization budgets remain valid.
- Total received-byte budget: 25 MiB, including failed response bodies.
- Resource limits: submissions 2 MiB; filing index 1 MiB; primary document 20 MiB.
- Concurrency: 1.
- Frequency: no more than one attempt per second, subject to any stricter current SEC rule.
- Timeouts: connect 10 seconds; idle read 30 seconds; total request 120 seconds.
- Redirects: 0. Any redirect aborts the plan.
- Cache: disabled for Gate B; cached or fixture data cannot count as live success.
- Grant lifetime: at most 30 minutes.
- Single-use execution approval lifetime: at most 10 minutes.

The current SEC access policy, identification requirements, request frequency, and reuse/storage terms must be reviewed against primary provider policy immediately before authorization. This document does not perform that online review.

## Credentials and request identity

No API key, bearer token, cookie, or authorization header is required or permitted. Gate B does require a declared SEC contact/User-Agent identity referenced by `SEC_EDGAR_CONTACT_IDENTITY` through the `DECLARED_CONTACT_IDENTITY` resolver.

The value is not a general secret, but it is sensitive operational configuration. It must be resolved only inside the authorized transport after all gates pass. Logs and audit records must contain only the reference metadata, never the resolved value, hash, prefix, suffix, request header, or environment value. Presence may be checked through the credential-reference resolver without disclosing the value, but the current committed composition has not configured that resolver for Gate B.

## Current implementation readiness

The repository contains the provider contract, deterministic SEC request-plan and response-validation adapter, endpoint validation, generic authorization/rate/budget/circuit-breaker machinery, safe HTTP client, artifact store, ingestion contracts, and Gate A tests.

It does not contain an activated production Gate B composition:

- `cli_live.py` binds the authorization application to an unconfigured factory.
- `cli_live.py` binds the SEC pilot application/transport to an unconfigured factory and returns `LIVE_TRANSPORT_NOT_CONFIGURED`.
- The SEC adapter builds and validates the finite plan but does not itself perform transport or persistence.
- The controlled-live tests exercise injected/fake harnesses and the blocked default path; they are not a production live transport.
- There is no operational production dry-run composition. Offline request construction and validation can be exercised, but that cannot validate DNS, TLS, current provider behavior, contact identity, HTTP response policy, or raw persistence.

Production provider implementation is therefore incomplete for Gate B execution. This preparation does not fill that gap.

## As-of and future-data contract

Evidence eligibility is determined by the source publication/filed/accepted/available timestamp required by the provider and evidence contract. It must be `<= research_as_of_time`. `retrieved_at` records acquisition only and cannot substitute for missing publication availability. A future-dated or temporally unverifiable artifact is BLOCKED/INVALID and cannot advance to a supported factual claim.

## Persistence, provenance, and transaction boundaries

The intended live path is:

`SEC provider -> request attempt -> raw artifact -> ingestion manifest -> DocumentVersion -> deterministic parse/chunk -> Citation verification -> Data Quality -> STOP`

Required audit/provenance includes:

- provider, capability, security, issuer, persisted CIK, exact endpoint/path, and request-attempt lineage;
- request/grant/approval identifiers and timestamps, response status, received bytes, MIME type, and failure code;
- opaque raw-blob reference, SHA-256 checksum, byte count, acquisition time, source publication/filed/accepted time;
- source record identifier, document/accession/form/period identity, synthetic status, and rights/license decision;
- adapter, parser, sanitizer, schema, and normalizer versions;
- manifest checksum/signature, record count, warnings, retention deadline, and deletion state.

Missing identity, checksum, raw reference, temporal eligibility, rights decision, or versioned parser/manifest lineage blocks admission. Transport, persistence, checksum, or database-integrity failures fail the pilot. The exact BLOCKED versus FAILED classification must follow the existing artifact/manifest/Data Quality contract; neither can be relabeled PASS.

Network I/O must not occur while a long database transaction is held. The intended boundary is a short atomic authorization/budget reservation, then network streaming and validation, then atomic artifact settlement and caller-owned persistence transactions. Failed requests consume approved request/byte budgets. A database failure removes only newly written unreferenced temporary bytes; safe request-attempt and incident audit is retained.

## Snapshot and downstream research boundary

Gate B itself creates no research Snapshot. If a later, separately authorized offline command creates one from admitted ingestion, it creates a new `BUILDING` Snapshot and seals it exactly once as `COMPLETE`, `PARTIAL`, or `FAILED`. A sealed Snapshot is immutable and cannot be overwritten. Failed Snapshots and safe audit artifacts are retained; correction is append-only.

Only a separately invoked production research workflow may proceed through Tool Invocation, Observation, EvidenceSource, `EvidenceLedgerService`, ResearchEvidence, deterministic Claim Builder, `ClaimSupportValidator`, Claim-Evidence links, Package, and Report. Direct provider-to-Evidence, provider-to-Claim, provider-to-Report, or direct insertion of VALID Evidence is prohibited. A live fetch does not imply VALID Evidence or a SUPPORTED factual Claim.

Synthetic, fixture, cached-test, or manual fallback can never masquerade as Gate B live success or support a real-company factual claim.

## Idempotency contract

The immutable execution plan checksum binds provider, capability, security, persisted CIK, form/accession/document, as-of, endpoints, budgets, and policy. Each attempt is idempotently consumed by `(authorization_id, request_attempt_id)`. The raw-artifact checksum and source-record identity provide content deduplication; the ingestion batch/manifest checksum and immutable DocumentVersion prevent duplicate normalized records.

A retry reuses the same approved plan and attempt lineage. An identical artifact may be deterministically reused without duplicate final records. A different checksum for the same immutable source identity is a conflict and aborts. Retry must not create a second Snapshot, Observation, Evidence, or Claim; those objects are outside the Gate B live command and are subject to their own repository uniqueness if later created.

## Failure matrix

In the table, “Run” means the controlled-live pilot outcome, not a Research Agent Run. Gate B creates no Snapshot or ResearchEvidence, so those columns remain `NOT_CREATED` unless a separately authorized later command is executed.

| Failure | Retry | Pilot outcome | Snapshot | ResearchEvidence | Human action |
|---|---|---|---|---|---|
| DNS failure | Once only if approved transient and budget remains | BLOCKED | NOT_CREATED | NOT_CREATED | Review network/provider status |
| Connect refused | Once only if approved transient and budget remains | BLOCKED | NOT_CREATED | NOT_CREATED | Review endpoint/network |
| Connect/read timeout | Once only if approved transient and budget remains | BLOCKED | NOT_CREATED | NOT_CREATED | Review provider health and budget |
| HTTP 403 | No | BLOCKED/ABORT | NOT_CREATED | NOT_CREATED | Recheck policy and request identity |
| HTTP 404 | No | BLOCKED/ABORT | NOT_CREATED | NOT_CREATED | Rebuild exact filing plan |
| HTTP 429 | No during the pilot | BLOCKED/ABORT; open/retain circuit state | NOT_CREATED | NOT_CREATED | Re-review provider policy and rate |
| HTTP 500/502/503/504 | At most the plan's single approved transient retry | BLOCKED if exhausted | NOT_CREATED | NOT_CREATED | Review provider health |
| Unexpected redirect | No | ABORT | NOT_CREATED | NOT_CREATED | Investigate endpoint/policy |
| Wrong content type | No | BLOCKED/FAILED | NOT_CREATED | NOT_CREATED | Inspect response without admitting it |
| Empty body | No | BLOCKED/FAILED | NOT_CREATED | NOT_CREATED | Inspect request/provider response |
| Malformed payload | No | BLOCKED/FAILED | NOT_CREATED | NOT_CREATED | Parser/provider review |
| Provider schema drift | No | ABORT | NOT_CREATED | NOT_CREATED | New reviewed adapter/plan required |
| Checksum mismatch | No | FAILED/ABORT | NOT_CREATED | NOT_CREATED | Integrity investigation |
| Future-dated artifact | No | BLOCKED/ABORT | NOT_CREATED | NOT_CREATED | Correct as-of/candidate plan |
| Issuer/security/CIK mismatch | No | FAILED/ABORT | NOT_CREATED | NOT_CREATED | Identity/security investigation |
| Duplicate identical artifact | No network retry | Deterministic reuse only | NOT_CREATED | NOT_CREATED | Verify dedup audit |
| Conflicting duplicate checksum | No | FAILED/ABORT | NOT_CREATED | NOT_CREATED | Integrity investigation |
| Parser failure | No live retry | PARTIAL/BLOCKED or FAILED | NOT_CREATED | NOT_CREATED | Offline parser review |
| Normalization failure | No live retry | PARTIAL/BLOCKED or FAILED | NOT_CREATED | NOT_CREATED | Offline normalizer review |
| DB persistence failure | No live retry | FAILED | NOT_CREATED | NOT_CREATED | Preserve audit; reconcile temporary object |
| Snapshot sealing failure | Not a Gate B live retry | Outside Gate B; later workflow FAILED | FAILED if separately created | No new admission | Retain failed Snapshot and audit |

No failure permits fixture, cached-test, synthetic, or unsupported factual fallback.

## Required audit fields

An executable pilot must expose, without credential/header values: plan checksum, grant ID, approval ID, request-attempt ID, provider/candidate, request time, response status, response size, MIME, checksum, raw artifact ID, ingestion manifest ID, DocumentVersion ID, parser/normalizer versions, citation IDs, Data Quality status, warnings, circuit/budget state, and stable failure codes.

The committed schema/contracts are sufficient to describe this audit trail, but the operational audit trail is not yet executable end to end because the production transport/application composition is absent.

## Success criteria

Gate B may return `LIVE_VALIDATION_PASS` only when all of the following are true:

- The exact disclosed plan is approved and no request occurs outside it.
- Actual attempts are within the 3-resource/4-attempt, byte, time, rate, and host budgets.
- Current SEC identity/access/reuse policy has been reviewed and the declared contact reference is safely configured.
- The exact filing identity, CIK, form, accession, report period, filing/publication time, and primary body are verified.
- Response MIME, byte size, SHA-256, raw blob, request attempt, and immutable manifest are persisted and reconcile.
- The artifact is nonfuture and rights permit the approved storage and derived use.
- Immutable DocumentVersion, deterministic parse/chunk, and at least one citation candidate validate.
- Data Quality has no unresolved blocking provenance/integrity defect.
- No synthetic/cache/fixture fallback, credential disclosure, redirect, unapproved host, model call, direct Evidence/Claim insertion, or unsupported factual Claim occurs.
- No unresolved CRITICAL or HIGH safety violation exists.

Success remains `LIVE_VALIDATION_PASS`; it does not activate production, publish a report, enter Stage 11, or authorize another provider/security/document.

## Abort criteria

Abort without widening scope for any candidate/provider/domain/credential ambiguity; plan-checksum mismatch; unexpected request or response host; any redirect; request/byte/time/rate overrun; policy or rights ambiguity; missing contact reference; 429; exhausted approved retry; schema drift; future-data conflict; security/issuer/CIK mismatch; checksum conflict; raw/manifest/database integrity failure; unexpected provider/live/model call; synthetic substitution; or any request not covered by the finite grant and single-use approval.

Failed pilot audit, request attempts, safe raw artifacts, circuit/budget state, and FAILED/BLOCKED records are retained according to policy. Audit data is not deleted to make the environment appear clean. Git rollback and data/audit retention are separate concerns.

## Human authorization boundary

Before any live call, a human must approve every concrete value below:

- provider and capability;
- security, issuer, symbol, exchange, and persisted CIK;
- exact form, accession, report period, filing date, index filename, and primary-document filename;
- exact allowed host/path list and GET-only method;
- research as-of time and temporal cutoff;
- three planned resources, four-attempt ceiling, one-retry policy, byte limits, timeouts, redirect prohibition, rate, and concurrency;
- declared contact credential reference and permission to resolve it without disclosure;
- raw-storage, excerpt, reuse, and retention decision;
- finite grant ID/lifetime and single-use approval ID/lifetime;
- explicit authorization for exactly this finite live plan.

Authorization template:

> I authorize Stage 10 Gate B for provider `SEC_EDGAR_PUBLIC_V1`, security `MU` / CIK `0000723125`, exact form `[10-K|10-Q]`, accession `[ACCESSION]`, report period `[DATE]`, filing date `[DATE]`, index `[FILENAME]`, primary document `[FILENAME]`, research as-of `[TIMESTAMP]`, hosts `data.sec.gov` and `www.sec.gov`, HTTPS GET only, 3 planned resources, at most 4 attempts and 1 approved transient retry, 25 MiB total, redirects 0, concurrency 1, rate at most 1 request/second, contact reference `SEC_EDGAR_CONTACT_IDENTITY`, retention decision `[DECISION]`, grant `[ID/EXPIRY]`, and single-use approval `[ID/EXPIRY]`. I authorize only this plan checksum `[SHA256]` and no model, Snapshot, Agent, Report, publication, Stage 11, or expanded provider activity.

A vague instruction such as “继续”, “运行”, “试一下”, “开始吧”, “continue”, “run it”, or “try it” is not authorization. Any changed parameter invalidates the approval and requires a new disclosure and decision.

## Pre-execution checklist

1. Confirm the reviewed Git commit and clean worktree.
2. Review current SEC primary policy and record the reviewed version/time.
3. Select and freeze the exact filing/accession/document and as-of.
4. Approve storage, excerpt, reuse, and retention semantics.
5. Configure the declared contact reference without reading or logging it during preparation.
6. Implement and independently verify the production authorization and SEC transport/application composition; repeat Gate A/static/offline tests for that change.
7. Produce the immutable three-resource plan and checksum.
8. Issue a finite real grant and matching single-use approval.
9. Obtain the exact human authorization above.
10. Perform exactly the authorized requests, validate and persist the raw artifact and manifest, parse offline, verify citations and Data Quality, then stop.
11. Reconcile attempts, bytes, audit IDs, warnings, and circuit/budget state for human review.

## Open blockers and verdict

Production blockers:

1. Production live-authorization application factory is unconfigured.
2. Production SEC pilot transport/application composition is unconfigured; only offline/fake harnesses and a blocked default path exist.

Safety blockers:

1. Current SEC policy and identification/rate/reuse requirements have not been re-reviewed for the execution date.
2. `SEC_EDGAR_CONTACT_IDENTITY` is not safely configured and presence-validated for the authorized transport.
3. Raw storage, excerpt/reuse, and retention decision is not final.

Operational blockers:

1. Exact form/accession/period/date/index/primary-document candidate is not selected.
2. No finite real Live Authorization Grant exists.
3. No matching single-use execution approval and exact human authorization exists.

Remote backup is not a formal Gate B prerequisite, and this repository currently has no configured remote.

**GATE_B_READINESS: NO_GO**

The next action is human review of this runbook and a separately scoped implementation/review step for the missing production authorization/transport composition. Gate B must not be authorized until all blockers are closed and the exact authorization template is fully instantiated.
