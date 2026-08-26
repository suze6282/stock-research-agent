# Stage 10 Gate B Phase 3E Attempt-Limit Contract Resolution

Status: **DESIGN / CONTRACT RESOLUTION COMPLETE**

Human approval: **PENDING**
Production correction: **NOT STARTED**
Phase 4A retry: **NOT STARTED**

Gate B readiness remains **NO_GO**. Gate B is not authorized or executed, and
Stage 11 has not started. This document freezes the correction required by the
fresh Phase 4A migration-built acceptance at repository state
`f2000fa9cac4f913a0a43966ce0ee66f43b2a94d`. It creates no RED test,
production behavior, migration, PostgreSQL schema change, operational filing
selection, or live capability.

## 1. Phase 4A evidence and acceptance result

Phase 4A created the disposable database
`stock_research_gate_b_acceptance_20260822_150702_test` on PostgreSQL 17.10 at
the repository-owned loopback endpoint. The database began with zero
application tables and was built only by `alembic upgrade head` through
`0012_component_observation_lineage_integrity`.

Column parity passed for the core Gate B tables, but behavioral constraint
parity failed:

| Evidence | Current contract |
|---|---|
| `ProviderRequestAttemptWrite.attempt_number` | `1..4` |
| `ProviderRequestAttempt` ORM CHECK | `1..3` |
| migration `0008` database CHECK | `1..3` |
| authorized SEC Gate B plan | at most 4 actual attempts and 1 retry |
| focused Gate B PostgreSQL fixture | no attempt-number bounds CHECK |

This produced two acceptance findings:

- **P4A-H01:** the approved Gate B controller can reserve attempt 4, but a
  migration-built production-equivalent database rejects its persistence.
- **P4A-H02:** commit `5f2a4a7` widened the shared
  `ProviderRequestAttemptWrite` type from 3 to 4, granting unrelated generic
  provider callers a semantic capability that belongs only to Gate B.

The fixture in `tests/integration/test_gate_b_sec_pilot_postgres.py` is more
permissive than production because its manual `provider_request_attempts` DDL
omits `ck_provider_request_attempts_bounds`. Phase 4A therefore failed and its
earlier assumption that Gate B enablement required no schema change is
superseded only for this proven constraint defect.

## 2. Approved physical and semantic limits

The following contracts are distinct and must not be collapsed:

| Boundary | Approved maximum | Meaning |
|---|---:|---|
| PostgreSQL physical row | 4 | Largest approved attempt identity the shared table can represent |
| SQLAlchemy ORM metadata | 4 | Exact parity with the migration-built table |
| Generic provider write/application boundary | 3 | Preserves the pre-Gate-B provider contract |
| Generic `ProviderPolicy.max_attempts` | 3 | Remains unchanged; it does not authorize Gate B attempt 4 |
| SEC Gate B reservation input | 4 | Available only inside an exact authorized Gate B execution |
| SEC Gate B plan-global retry count | 1 | Attempt 4 does not create another retry token |

`PHYSICAL_STORAGE_MAX` may be greater than `GENERIC_PROVIDER_SEMANTIC_MAX`.
The database's ability to store a value is not permission for an application
caller to create it.

`ProviderRequestAttemptWrite` must return to `Field(ge=1, le=3)`. Because
`ProviderRequestAttemptRecord` currently inherits that write type, the record
contract must be decoupled from the generic write contract: a persisted record
must be able to represent physical attempt 4 without making attempt 4 valid as
generic input. Reading or projecting a physical row is not an authorization
operation.

## 3. Gate B-specific validation owner

The selected semantic owner is the existing
`SqlAlchemySecAttemptReservationPort`, specifically its `_reserve_attempt`
boundary, consuming the existing `SecAttemptReservationRequest`.

This is the smallest authoritative owner because it already:

- requires `AuthorizedGateBExecution` before a normal reservation;
- binds authorization ID, plan ID, plan checksum and Sync Run;
- accepts the SEC-specific `SecAttemptReservationRequest`, whose bounded
  attempt number is `1..4`;
- enforces plan-global attempt sequence, total attempt capacity and the single
  retry budget inside the pre-send transaction; and
- produces `SecAttemptPermit` only after the reservation commits.

The future implementation must give this port a dedicated Gate-B persistence
path for the attempt row after those checks. It must not send attempt 4 through
the generic `ProviderRequestAttemptWrite` or expose a generic
`allow_attempt_four=True` switch. Generic
`SqlAlchemyProviderSyncRepository.append_attempt` and its ordinary
`reserve_attempt` input remain limited by `ProviderRequestAttemptWrite` to
attempts 1 through 3.

An attempt-4 insert is valid only when all of the following are authoritative:

- execution is an `AuthorizedGateBExecution` for `SEC_EDGAR_PUBLIC_V1`;
- the exact plan ID and checksum match;
- the request resource belongs to that plan and Sync Run;
- the execution envelope has `max_actual_attempts = 4` and `max_retries = 1`;
- the request is the next permanent attempt identity; and
- the plan-global capacity and retry reservation commit before `send_start`.

No caller-provided boolean or unscoped repository flag can substitute for this
context.

## 4. ORM and migration contract

One narrow migration is required after the current head. Its planned revision
is `0013_gate_b_attempt_number_capacity` with
`down_revision = 0012_component_observation_lineage_integrity`.

Upgrade behavior is limited to `provider_request_attempts`:

1. Drop the named CHECK `ck_provider_request_attempts_bounds`.
2. Recreate the same named CHECK with `attempt_number BETWEEN 1 AND 4`.
3. Preserve the existing `response_bytes >= 0` and optional HTTP status
   `100..599` clauses exactly.

The matching ORM `CheckConstraint` must use the same `1..4` physical bound. The
migration adds no column or table and changes no other constraint, index,
default, foreign key or provider policy.

## 5. Downgrade contract

The repository permits data-aware downgrade refusal. Migration `0011` already
queries authoritative rows and raises when existing data cannot satisfy the
older schema, while the Stage 10 design permits database downgrade only before
retained Stage 10 evidence exists or after an explicit export/deletion review.

Accordingly, downgrade must:

1. Count rows in `provider_request_attempts` with `attempt_number = 4`.
2. If any exist, raise a stable migration error such as
   `GATE_B_ATTEMPT_FOUR_PREVENTS_DOWNGRADE` before altering the CHECK.
3. If none exist, replace the `1..4` CHECK with the original `1..3` CHECK,
   preserving its remaining clauses and name.

Downgrade must never delete, renumber or rewrite attempt lineage. Operators may
retry downgrade only after the separately governed export/deletion review makes
the older constraint truthful. This is a fail-closed downgrade, not a data
cleanup feature.

## 6. Fixture parity contract

Schema-sensitive Gate B acceptance must prefer an empty PostgreSQL database
built from committed migrations. Focused schema fixtures may remain for test
speed only if their attempt-number CHECK is semantically identical to the
current production migration and ORM metadata.

The manual fixture in `test_gate_b_sec_pilot_postgres.py` must therefore add
the production-equivalent constraint when Phase 3E implementation begins. It
must prove that 4 is accepted and 5 is rejected. A fixture may be stricter than
a particular test's input, but it must never be more permissive than production
for `attempt_number`.

## 7. Future offline RED contracts

No test is created by this resolution. Phase 3E-1 must establish these tests
before any production or migration change:

### RED-062 — migration-built Gate B attempt 4

Starting from an empty disposable loopback PostgreSQL database, run the real
migrations and reserve/persist attempt 4 through the authoritative Gate B path.
The current expected RED is the production database CHECK rejecting 4.

### RED-063 — migration-built physical upper bound

Against the same migration-built schema, direct persistence of
`attempt_number = 5` must fail at the database constraint. The physical upper
bound remains exactly 4.

### RED-064 — generic provider semantic upper bound

At the ordinary non-Gate-B `ProviderRequestAttemptWrite` boundary, prove that
attempts 1, 2 and 3 validate and attempt 4 is rejected. Existing tests cover
ordinary attempt-1 construction and repository persistence, but no current test
proves the generic 3/4 boundary, so this RED is required.

### RED-065 — authoritative Gate B-only attempt 4

Prove that attempt 4 can be persisted only through
`SqlAlchemySecAttemptReservationPort` with matching
`AuthorizedGateBExecution`, exact plan/checksum/resource/Sync Run scope and an
approved remaining attempt budget. Generic write input, missing execution,
mismatched execution and unapproved scope must fail before persistence and
before send.

### RED-066 — focused fixture/schema parity

Inspect or exercise the focused Gate B fixture's named attempt constraint and
compare its behavior with a migration-built database: both accept 4 and reject
5. The fixture cannot omit the production bound.

### RED-067 — full four-attempt migration-built scenario

Against a database created by real migrations, run the offline injected Gate B
orchestrator with one authorization, one plan and one Sync Run:

1. attempt 1 — resource 0;
2. attempt 2 — resource 1 first try;
3. attempt 3 — the one plan-global retry for resource 1; and
4. attempt 4 — resource 2.

The fourth attempt must persist, all resources must retain exact order and
scope, retry count must remain one, and the aggregate Gate B result must reach
its existing terminal offline completion boundary without external network.

## 8. Required regression preservation

Phase 3E implementation cannot be accepted unless:

- RED-062 through RED-067 are GREEN against their correct owners;
- RED-028 through RED-061 remain GREEN;
- generic provider tests prove the 1/2/3 accepted and 4 rejected boundary;
- migration upgrade from empty database and schema/ORM parity pass;
- downgrade succeeds with no attempt-4 rows and fails closed when attempt-4
  lineage exists; and
- no Gate B attempt can reach DNS or `send_start` without the existing
  authoritative execution and permit chain.

## 9. Explicit non-goals and safety state

This contract does not authorize:

- production, ORM, migration, test or fixture implementation;
- changes to generic retry or timeout behavior;
- increasing `ProviderPolicy.max_attempts` above 3;
- a generic attempt-4 flag or capability;
- data deletion, renumbering or automatic downgrade cleanup;
- a new table, column or unrelated constraint;
- SEC requests, DNS, external network or credential/contact resolution;
- filing/accession freeze, Gate B authorization or Gate B execution; or
- Phase 4A retry, Phase 5 or Stage 11.

Safety remains: external network 0, external DNS 0, credential value reads 0,
SEC/live calls 0, Gate B readiness `NO_GO`, Gate B authorized `NO`, Gate B
executed `NO`, and Stage 11 `NOT STARTED`.
