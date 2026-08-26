# Stage 10 Live Authorization Matrix

Status: design-only register; no grant exists and no Live execution is approved.

This matrix extends the Stage 9 Provider Capability and License Matrix without
changing any Provider state. Public accessibility is not an authorization.

## 1. Provider decision matrix

| Provider | Candidate capability | Current production state | Stage 10 design decision | Live state |
|---|---|---|---|---|
| `SEC_EDGAR_PUBLIC_V1` | submissions metadata, exact filing index, exact primary document | `CONDITIONAL` | Eligible only for one separately approved finite pilot | `NOT_ATTEMPTED` |
| `TUSHARE_PRO_V1` | A-share structured data | `BLOCKED` / `RESTRICTED_REVIEW_REQUIRED` | Not eligible; no credential, entitlement or storage/use rights may be inferred | `NOT_ATTEMPTED` |
| `SSE_DISCLOSURE_V1_CANDIDATE` | official disclosure body automation | `BLOCKED` | Not eligible; manual user-supplied official file is a different `NOT_LIVE` path | `NOT_ATTEMPTED` |
| `SZSE_DISCLOSURE_V1_CANDIDATE` | official disclosure body automation | `BLOCKED` | Not eligible | `NOT_ATTEMPTED` |
| `CNINFO_DISCLOSURE_V1_CANDIDATE` | official disclosure body automation | `BLOCKED` | Not eligible | `NOT_ATTEMPTED` |
| `LICENSED_US_EOD_UNSELECTED` | U.S. EOD market data | `BLOCKED` | Not eligible; vendor and rights are absent | `NOT_ATTEMPTED` |
| `PRODUCTION_EMBEDDING_UNSELECTED` | production embedding | `BLOCKED` | Not eligible; no provider/model/cost/data policy | `NOT_ATTEMPTED` |
| `CONTROLLED_MANUAL_EVIDENCE_V1` | local user-supplied file intake | proposed `CONDITIONAL` local-only definition | Gate A only after design approval; always `requires_network=false` and `NOT_LIVE` | `NOT_LIVE` |

## 2. SEC candidate scope

The candidate is not a created or approved grant. A later plan may reduce these
limits but cannot increase them without returning to user approval.

| Field | Frozen candidate value or derivation |
|---|---|
| Provider | `SEC_EDGAR_PUBLIC_V1`, exact persisted definition/version/checksum |
| Security | `MU`, security `40000000-0000-0000-0000-000000000002` |
| Issuer | `30000000-0000-0000-0000-000000000002` |
| Provider identifier | CIK `0000723125`, resolved from persisted `SEC_CIK` |
| Capability | exact persisted capabilities needed for submissions and filing documents only |
| Form | one exact `10-K` or `10-Q`, selected and disclosed before approval |
| Accession | one exact normalized accession obtained from validated persisted/planned metadata |
| Date window | exact selected filing date/report period; no open-ended range |
| Documents | one submissions JSON, one filing index, one primary filing document |
| Company Facts | excluded from first pilot |
| Exhibits/complete submission | excluded |
| Domains | exact `data.sec.gov` and `www.sec.gov` only |
| Methods | `GET` only |
| Paths | concrete expanded paths from Stage 9 endpoint policy; no operator URL |
| Planned resources | 3 |
| Actual request-attempt limit | 4, including failed attempts and retry |
| Retry | at most 1 across the entire plan, transient allowlist only |
| Total byte limit | 26,214,400 bytes (25 MiB), including failed bodies |
| Per-resource byte limits | submissions 2 MiB, filing index 1 MiB, primary document 20 MiB |
| Concurrency | 1 |
| Rate | at most 1 actual attempt per second, subject to stricter current official rule |
| Timeouts | connect 10 s, idle read 30 s, run 120 s |
| Redirects | 0 |
| Grant lifetime | at most 30 minutes after activation |
| Execution approval lifetime | at most 10 minutes; one plan checksum; single use |
| Cache | disabled |
| Raw storage | required; execution blocks if not approved |
| Default retention | at most 30 days and never beyond license/grant decision |
| Estimated direct Provider cost | zero monetary API fee based on the current public-source design; this must be revalidated before execution |
| Estimated execution time | no more than the 120-second hard runtime, excluding operator review |

The sum of per-resource maxima is a per-resource ceiling; the lower 25 MiB total
limit always wins. The remaining 2 MiB is not reusable to exceed the primary
document's 20 MiB cap.

## 3. Exact authorization content

A grant is valid only when all of these are non-empty, canonical and checksum-bound:

- authorization, Provider definition and Capability IDs and versions;
- Security, issuer and normalized CIK;
- exact form, accession, filing/report dates and primary document name;
- exact official domains, methods and expanded paths;
- request, retry, byte, duration, redirect and concurrency limits;
- Provider, endpoint and license policy IDs/versions/checksums;
- credential/contact reference and User-Agent reference;
- raw storage, cache, derived use, excerpt, redistribution and retention decisions;
- actor, approval time, expiry and canonical checksum.

Missing data yields `DRAFT` or `BLOCKED`; it is not defaulted from a prompt or
latest-record shortcut.

## 4. Lifecycle matrix

| Derived state | Entry condition | Allowed action | Forbidden action |
|---|---|---|---|
| `DRAFT` | immutable scope created but approvals incomplete | show, cancel | activate, execute, resolve contact |
| `APPROVED` | license/policy and user approval recorded | activate before expiry | execute before activation, change scope |
| `ACTIVE` | exact execution approval matches and all gates pass | consume finite budget, revoke | enlarge budget, cross scope |
| `CONSUMED` | plan complete or finite budget exhausted | show/audit | reactivate or execute |
| `EXPIRED` | grant or execution approval time elapsed | show/audit | execute or renew in place |
| `REVOKED` | emergency/operator revocation event | stop/audit | execute or reactivate |
| `CANCELLED` | pre-execution cancellation | show/audit | activate or execute |

All transitions are append-only events. `CONSUMED`, `EXPIRED`, `REVOKED` and
`CANCELLED` are terminal. A new attempt requires a new grant and approval.

## 5. Consumption rules

1. Every actual HTTP attempt reserves one request before socket creation.
2. Actual bytes are charged while streaming; all received bytes count even when
   parsing or status validation later fails.
3. A retry consumes a new request and shares the single total retry allowance.
4. Request/byte/duration checks are atomic under a grant-scoped PostgreSQL lock.
5. An attempt cannot use another Provider, Capability, Security, CIK, host, path,
   method, accession or document.
6. Expiry/revocation is checked before DNS, before socket creation and between
   response chunks.
7. A crash after possible socket creation does not refund a request.
8. Checkpoint advances only in the same successful transaction that admits the
   complete artifact/manifest.

## 6. Credential and contact identity matrix

| Item | Persisted | Resolved | Returned/logged | Decision |
|---|---:|---:|---:|---|
| Credential reference ID/version/status/safe label | Yes | Not needed | Safe summary only | Allowed |
| SEC declared contact identity value | No | Only after ACTIVE grant and all earlier gates | Never | Required for pilot |
| API token/key/cookie/Authorization value | No | No for SEC pilot | Never | Forbidden |
| Hash/prefix/suffix of a credential/contact value | No | No | Never | Forbidden |
| Environment variable existence | Safe status may be checked only at authorized configuration gate | Does not activate Provider | Safe boolean/status only | Insufficient by itself |

The design stage and Gate A do not resolve any real contact or credential value.

## 7. License action matrix

| Use | SEC candidate | Manual official document | Manual unverified document |
|---|---|---|---|
| Acquire/read bytes | Requires current official-policy review and ACTIVE grant | Requires user declaration and local import approval | Quarantine inspection only |
| Raw storage | Must be explicitly allowed | Must be explicitly allowed | Minimal quarantine retention only |
| Cache | Disabled | Not applicable | Not applicable |
| Parse/chunk | Requires derived-use decision | Requires derived-use decision | Validation only; not company evidence |
| Excerpt/Citation | Requires excerpt/derived-use decision | Requires excerpt decision | Forbidden for VALID Citation |
| Internal research | Requires derived-use decision | Requires company-research approval | Forbidden |
| Redistribution/public report | Not granted by this design | Not granted by this design | Forbidden |
| Retention | Minimum of grant, policy and declaration | Minimum of review and declaration | Short quarantine deadline |
| Deletion | Append-only action, remove bytes/cache | Append-only action, remove bytes | Delete or retain quarantined metadata only per declaration |

Any `UNKNOWN_REQUIRES_REVIEW`, prohibited, expired or contradictory field blocks
the corresponding use.

## 8. Live execution disclosure required before approval

Before asking for `批准执行该SEC有限Live验证`, the system/operator must display:

1. Provider definition/version/checksum;
2. Security and issuer IDs;
3. CIK and identity source;
4. exact Capability IDs/versions;
5. filing form, accession, dates and primary filename;
6. exact domains, methods and concrete paths;
7. planned resources and actual-attempt limit;
8. total and per-response byte limits;
9. rate, concurrency, redirect and timeout limits;
10. grant and execution-approval expiry;
11. contact reference status without its value;
12. current license review, source IDs and decisions;
13. raw storage, cache, excerpt and redistribution decisions;
14. retention deadline;
15. expected direct cost and maximum runtime;
16. database/table writes;
17. blob artifacts and their maximum size;
18. rollback and temporary-file cleanup;
19. restricted-data deletion procedure;
20. incident and emergency-stop command;
21. Snapshot/Agent/Report explicitly excluded from the Live command; and
22. all Providers/capabilities that remain blocked.

Approval for any different plan is invalid for this grant.

## 9. Stage status interpretation

- `LIVE_VALIDATION_PASS`: the exact approved resources were acquired and their
  artifact/manifest/document/Citation readiness passed.
- `LIMITED_PRODUCTION_PILOT`: a later, separately reviewed limited operating mode;
  not conferred by the first run.
- `PRODUCTION_READY`: broader supported scope, rights, operations and reliability
  evidence; not conferred by this stage design.
- `PRODUCTION_ACTIVE`: explicit production activation; outside this design.

No offline fixture or manual import can set a SEC Live status.
