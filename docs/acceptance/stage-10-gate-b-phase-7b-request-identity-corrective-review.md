# Phase 7B Gate B Request Identity Corrective Review

## Verdict

`PHASE_7B_1G_CORRECTIVE_REVIEW: COMPLETE`

`REVIEW_VERDICT: PASS`

The corrective implementation resolves the prior public-builder validation-boundary defect without changing the approved request checksum, idempotency, request/plan layering, generic attempt boundary, or secret and I/O isolation contracts. This review does not complete Operational Freeze and does not authorize or execute Gate B.

## Reviewed lineage

| Role | Commit |
| --- | --- |
| Original implementation | `2aeed8e5ad33c74e9f8084136bfb71164241adbb` |
| Corrective RED baseline | `608f80721ea6515e8a1dc3b40e3c411565e2fc1d` |
| Corrective implementation | `b5f97203c538d7303604871e879b3c1f6d569ffb` |

The exact corrective diff contains one production file only:

`src/stock_research_agent/domain/live_evidence/gate_b_request_identity.py`

No tests, migrations, configuration, or documentation were changed by the corrective implementation commit.

## Previous finding and root cause

`IMPORTANT-01` found that `build_gate_b_sync_request()` trusted an already-constructed `GateBSyncRequestIdentity`. Pydantic operations that bypass validation, including unchecked construction and `model_copy(update=...)`, could therefore preserve an invalid Gate B state while retaining the expected Python type and cross the public builder boundary.

The correction extracts safe Python data with `model_dump(mode="python")`, constructs and validates a new `GateBSyncRequestIdentity`, and uses only that `fresh_identity` for the request checksum, idempotency payload, and `ProviderSyncRequestWrite` mapping. It does not call `model_validate()` directly on the existing model instance.

## Independent boundary evidence

| Review property | Result |
| --- | --- |
| Fresh model reconstruction | PASS |
| Prior validation state trusted | NO |
| Nested `GateBSyncRequestScope` validation rerun | PASS |
| Copied `OFFLINE` execution mode | REJECTED |
| Copied invalid security/universe state | REJECTED |
| Non-SEC provider scope | REJECTED |
| Noncanonical CIK | REJECTED |
| Noncanonical accession | REJECTED |
| Invalid SEC form | REJECTED |
| Unchecked constructed identity | REJECTED |
| Fail-closed typed validation | YES |
| Broad exception swallowing | NO |
| Fallback to unvalidated input | NO |

These checks exercised the public `build_gate_b_sync_request()` boundary directly with synthetic, secret-free inputs. An independent spy at the request-mapping seam also confirmed that the mapped identity was a distinct freshly validated model instance.

## Downstream identity authority

| Authoritative operation | Source |
| --- | --- |
| Request checksum | `fresh_identity` |
| Idempotency payload | `fresh_identity` |
| `ProviderSyncRequestWrite` field mapping | `fresh_identity` |

The original caller-supplied object is not used downstream after reconstruction.

## Semantic stability

| Contract | Result |
| --- | --- |
| Request checksum independently recomputed | MATCH |
| Request checksum inputs | UNCHANGED |
| Idempotency key independently recomputed | MATCH |
| Idempotency namespace | `GATE_B_LIVE_VALIDATION_SYNC_REQUEST` |
| Idempotency version | `1.0.0` |
| Valid canonical request fields | UNCHANGED |
| Request/plan layering | PASS |
| Plan checksum invoked by request builder | NO |
| Generic `ProviderSyncRequest` attempt boundary | PASS (`<= 3`) |
| Gate B attempt 4 leaked into request identity | NO |

The four-attempt, one-retry Gate B physical envelope remains an authorization/controller concern and was not moved into generic request identity.

## Secret and I/O isolation

Static inspection of the effective module found no raw contact material, environment reads, credential resolution, `User-Agent` or header construction, network access, database access, filesystem I/O, randomness, or wall-clock calls. No secret-bearing value is introduced into checksum or idempotency material.

## Corrective test quality

| Contract | Evidence quality |
| --- | --- |
| RED-012 copied `OFFLINE` bypass | PASS |
| RED-013 security/universe bypass | PASS |
| RED-014 provider, CIK, accession, and form variants | PASS |
| RED-015 unchecked construction | PASS |
| RED-016 exact namespace and version | PASS |

All corrective contracts reach `build_gate_b_sync_request()`; none can pass solely through model-level validation outside the public builder. The original RED-001 through RED-011 contracts remain preserved, including canonical equivalence, significant request fields, secret exclusion, replay conflict, offline separation, determinism, credential-reference and license-policy significance, and the generic attempt boundary.

## Fresh verification

| Verification | Result |
| --- | --- |
| Corrective boundary suite | 8 passed |
| Original RED-001 through RED-011 | 11 passed |
| Module-boundary suite | 14 passed |
| Combined fresh pytest invocation | 33 passed |
| Ruff on affected source and corrective test | PASS |
| Ruff format check on affected source and corrective test | PASS (2 files) |
| Mypy on affected source | PASS (1 source file) |
| Corrective commit-range `git diff --check` | PASS |

The PostgreSQL test used only the repository loopback test database. No operational database, external network, operational freeze record, authorization, or Gate B execution was used.

## Security review

The exact corrective range received complete one-file security diff coverage. Adversarial execution, supporting-model inspection, focused tests, and static checks produced no plausible reportable security candidate.

| Severity | Count |
| --- | ---: |
| CRITICAL | 0 |
| IMPORTANT | 0 |
| MINOR | 0 |

The previous `IMPORTANT-01` finding is resolved.

## Final state

| State | Value |
| --- | --- |
| Ready to return to Operational Freeze | YES |
| Operational Freeze | INCOMPLETE |
| Ready for Gate B authorization review | NO |
| Gate B authorized | NO |
| Gate B executed | NO |
| Stage 11 | NOT_STARTED |
| Human review required | YES |
