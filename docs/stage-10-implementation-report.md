# Stage 10 Controlled Live Evidence — Gate A Implementation Report

## 1. Gate A conclusion

Gate A status: `GATE_A_COMPLETE`. Stage 10 overall: `CONDITIONAL GO`.
Every Task 80 quality and migration gate passed. Gate B: `NOT_ATTEMPTED`; no
Live PASS is claimed.

## 2. Current branch

`stage-10/controlled-live-evidence`; it is not merged into `main`.

## 3. Design approval

Implementation follows the four approved Stage 10 design/runbook documents and
route C: finite SEC pilot plus controlled offline A-share manual evidence intake.

## 4. Task completion

Task 1–80: `80/80`.

## 5. Database tables

Fifteen tables separate grants/events/consumption/approval, manual intake and
review, manifests/Snapshot binding, real-company validation, retention and
incidents. Their exact names are documented in `docs/database.md`.

## 6. Alembic

Migration `0009_controlled_live_evidence` is implemented with named constraints,
indexes, RESTRICT lineage, immutability triggers and full Stage 10 downgrade.
Task 80 verified `0008 → 0009 → 0008 → 0009`; Final revision: `0009_controlled_live_evidence (head)`.

## 7. LiveAuthorizationGrant

Immutable canonical scope and append-only state events enforce exact Provider,
capability, Security, identifiers, methods, policy versions, budgets and expiry.

## 8. Consumption

Request attempts reserve and settle single-use consumption atomically; retries
consume the same finite budget and cannot create free capacity.

## 9. Execution Approval

Approvals are checksum-bound, expire within ten minutes, are single-use, and fail
on grant/plan mismatch or replay.

## 10. Atomic budgets

PostgreSQL row locks and unique attempt identity enforce request and byte limits
under concurrency. Duration, retry and grant lifetime are finite.

## 11. Manual Import

The explicit state chain is plan, receive, quarantine, validate, review,
approve/reject, ingest. It never fabricates HTTP, Provider Sync or Live lineage.

## 12. File security

PDF active content/attachments, HTML active/external content, unsafe paths/names,
MIME/magic mismatch, archives/executables and bounded JSON violations fail closed.
OCR is absent and files are limited to 25 MiB.

## 13. Raw Artifact

Provider and manual evidence reuse immutable raw storage while retaining mutually
exclusive source identity. Original bytes/checksum are never overwritten.

## 14. Ingestion Manifest

Canonical immutable manifests bind source type, Security/issuer, raw artifact,
rights, temporal metadata, review, synthetic status and checksum.

## 15. Snapshot

Plan and create are separate explicit operations. Security/issuer/as-of/licensing,
future-data and synthetic-contamination rules are enforced; terminal history and
bindings remain immutable. Gate A creates only test-scoped synthetic Snapshots.

## 16. Agent

Execution requires an explicit sealed Snapshot and existing Stage 7 application.
Tools remain read-only/offline; no Credential, Provider sync, network or model is
available. No real-company Agent Run was executed.

## 17. Report

Generation requires an explicit sealed Package and existing Stage 8 application,
creates a new version, and cannot bypass Reflection or Release Gate. No real-company
Report was generated.

## 18. CLI

Authorization, SEC plan, manual evidence, Snapshot, Research Run and Report commands
are separated. Every write is explicit; no one-command Live→Report chain exists.

## 19. API

Ten `/api/v1/live-evidence` routes are GET-only, bounded and safe. There is no
Stage 10 POST/PUT/PATCH/DELETE surface.

## 20. Fixture

Synthetic PDF/HTML/JSON attack fixtures use LF, verified checksums and all four
markers: `SYNTHETIC_TEST_ONLY`, `NOT_COMPANY_EVIDENCE`, `OFFLINE`, `NOT_LIVE`.

## 21. Default network status

External DNS/socket and Provider/model transport: `BLOCKED`. Loopback PostgreSQL
is the only network used by default tests.

## 22. Credential access status

Credential values read: `NO`. SEC contact identity read: `NO`.

## 23. Live request status

Live requests executed: `NO`. SEC, Tushare, exchanges, U.S. EOD and model endpoints
were not contacted.

## 24. Ruff

`uv run ruff check .`: PASS (`All checks passed!`).

## 25. Format check

`uv run ruff format --check .`: PASS (`645 files already formatted`).

## 26. mypy

`uv run mypy src`: PASS (`Success: no issues found in 280 source files`).

## 27. pytest

Task 80 full regression: `2980 passed, 0 failed, 0 errors, 0 skipped, 0 warnings`;
duration `501.06s (0:08:21)`.

## 28. PostgreSQL

PostgreSQL 17.10 development `stock_research` and test `stock_research_test` are
separate loopback databases. Both finished at `0009_controlled_live_evidence`,
contain all 15 Stage 10 tables and 106 total tables, and retained all checked Stage
2–9 sentinels. Development Stage 10 row count is 0; there is no test-schema or
process residue.

## 29. Reflection Round 1

Five HIGH findings were discovered and closed; two MEDIUM architecture/CLI
limitations were accepted and documented. No CRITICAL was found.

## 30. Reflection Round 2

Round 2 rechecked all five HIGH IDs against static, focused PostgreSQL and full
regression evidence. Gate B and real-company work remained untouched.

## 31. Fixed findings

`S10-R1-001`, `S10-R1-002`, `S10-R1-003`, `S10-R1-004` and `S10-R1-007` are
closed: format/imports, timezone types, parent list queries, lineage FKs and full
suite evidence now pass.

## 32. Unresolved CRITICAL

unresolved CRITICAL=0.

## 33. Unresolved HIGH

unresolved HIGH=0.

## 34. Gate B blockers

No exact Gate B authorization, chosen filing/accession, current SEC-rule review,
configured contact identity, approved retention decision, finite real Grant,
single-use execution approval or production transport exists.

## 35. SEC filing selection

No concrete 10-K or 10-Q filing has been selected. Company Submissions metadata
cannot substitute for the filing body.

## 36. SEC accession selection

No concrete accession is selected or authorized for Live retrieval.

## 37. SEC rules revalidation

Current official SEC access rules must be revalidated immediately before any Gate
B request; Gate A did not use external network access to do so.

## 38. SEC contact identity

The SEC User-Agent/contact identity remains `NOT_READ` and unconfigured for Gate B.

## 39. Retention approval

Candidate raw storage/cache/retention/deletion terms require final approval before
Live execution; Gate A only validates deterministic policies with synthetic bytes.

## 40. Industrial FII real file

No approved Industrial FII disclosure body was supplied or imported. Status:
`BLOCKED`.

## 41. Real Snapshot

No real Industrial FII or Micron production Snapshot was created.

## 42. Real Agent

No real-company Research Agent was run. Synthetic integration proves engineering
behavior only.

## 43. Real Report

No real-company Report, rating, target price, advice or trading output was generated.

## 44. Gate B application readiness

Gate A engineering is complete, so a concrete finite SEC plan may be prepared for
user review. Gate B execution remains unauthorized until all 24 required fields are
disclosed and the user supplies the exact approval phrase.

## 45. Stage 11

Stage 11 was not started and is not authorized by this report.
