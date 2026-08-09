# Stage 8 Verifiable Report and Runtime Reflection Implementation Report

## 1. Stage conclusion

**CONDITIONAL GO**

The deterministic report, Claim-level reference, runtime Reflection, subtractive
Revision, internal Release Gate, persistence, read-only query, and explicit CLI
engineering gates pass. The condition is evidentiary and operational: Industrial
FII and Micron still lack sufficient approved company-body and financial evidence,
production Narrative and Reflection providers are not configured, and previously
blocked Live providers remain blocked. No complete real-company investment report
has been produced.

## 2. Current branch

The implementation is on `stage-8/verifiable-report-reflection`. It has not been
merged to `main`, pushed, or used to start Stage 9.

## 3. Design approval record

The user approved
`docs/specs/stage-8-verifiable-report-reflection-design.md` with the phrase
`批准设计并继续实现`. The approved route is the controlled hybrid architecture:
deterministic production behavior with model-provider ports remaining disabled.

## 4. Implemented scope

Tasks 0–50 implement one immutable Stage 7 Research Package input, versioned report
policies and templates, deterministic JSON/Markdown rendering, exact Claim,
Evidence, and Citation bindings, two bounded Reflection rounds, one bounded
subtractive Revision, an internal Release Gate, 15 PostgreSQL tables, ten read-only
Tools, ten GET routes, explicit CLI workflows, bilingual templates, secure export,
real-company degradation tests, and an isolated Synthetic flow.

## 5. Excluded scope

No model call, Research Agent rerun, Tool execution during generation, provider
refresh, Snapshot rebuild, calculation, parsing, retrieval, indexing, Embedding
generation, unsupported currency conversion, rating, target price, forecast,
portfolio advice, trading signal, broker integration, automatic publication, PDF,
frontend, MCP Server, or Stage 9 capability was added.

## 6. Report architecture

`DeterministicReportCompositionService` consumes an exact persisted package and
approved immutable policy/template versions. It creates a canonical structured
report and a Markdown projection, validates the full binding graph, and persists
the aggregate transactionally. Query adapters are separated from all write
workflows.

## 7. Input contract

`ReportInputManifest` records the exact Research Package, Security, Snapshot,
as-of time, Policy, template, locale, tool catalog, Claim, Evidence, Citation,
calculation, retrieval, and source checksums actually used. Cross-security,
cross-Snapshot, future, unused, missing, or Synthetic-contaminated real-company
inputs are rejected. There is no “latest” lookup.

## 8. Report Policy

The fixed, versioned Policy controls report type, locale, section set, factual
binding requirements, status handling, limits, and permitted output. It cannot
authorize advice, model use, networking, publication, or source mutation.

## 9. Template

Templates are immutable, versioned data definitions with a finite section order
and block types. Template data cannot execute code, alter permissions, add sources,
override controlled context, or introduce unbound factual text.

## 10. Generation Run

Generation Runs use a finite lifecycle, record exact versions and checksums, and
become immutable at terminal state. A failed or partial input is represented
honestly; generation does not repair or enrich its source package.

## 11. Report versions

Reports are immutable versions linked by `previous_report_id`. Revision and
release sealing create new versions and never edit the prior report. Surviving
Claim/Evidence/Citation bindings are deterministically rebased to the new version.

## 12. Section

Sections have stable keys, deterministic order, explicit status, and bounded
content. Empty or unavailable sections state `NOT_REQUESTED`, `NO_EVIDENCE`,
`BLOCKED`, or `PARTIAL` rather than inventing prose.

## 13. Block

Blocks are typed, ordered, immutable report units. Factual paragraphs, bullets,
metrics, Claim index entries, and appendix rows must be covered by the persisted
binding graph. Non-factual limitation blocks remain visibly classified.

## 14. Claim Binding

Every factual report location binds to an exact persisted Stage 7 Claim. The
repository rejects a factual aggregate without complete Claim bindings, and the
composition service persists bindings atomically with the report.

## 15. Evidence Binding

Each report Evidence binding follows an existing Stage 7 Claim-Evidence Link and
retains Security, Snapshot, as-of, synthetic status, checksum, and structured
lineage. Unsupported, future, invalid, or cross-context evidence cannot silently
support a factual block.

## 16. Citation Binding

Document Evidence binds to an exact VALID Citation and immutable
DocumentVersion. Invalid Citations, unknown strict-history publication times,
future evidence, and Synthetic evidence in real-company reports are rejected.

## 17. JSON Renderer

Canonical JSON is the authoritative representation. Field order, list order,
Decimal strings, time serialization, reference labels, and checksums are stable
for the same approved input and versions.

## 18. Markdown Renderer

Markdown is generated only from the canonical structured report. It cannot add
facts or references. Its checksum is persisted and verified before CLI export;
export is restricted to the configured root and does not overwrite by default.

## 19. zh-CN

The `zh-CN` templates provide deterministic localized headings, status labels,
units, periods, limitations, references, and appendices without changing source
meaning or binding identity.

## 20. en-US

The `en-US` templates provide the same section and binding semantics as `zh-CN`.
Locale changes presentation only; facts, Decimal values, periods, currencies,
checksums, and source identity are not inferred or converted.

## 21. Reference format

Stable first-appearance labels use `[CIT-001]`, `[EV-001]`, `[MET-001]`,
`[LIM-001]`, and `[CON-001]`. There is no probabilistic confidence score or
unbound footnote.

## 22. Evidence appendix

The production composition path creates an Evidence appendix from the validated
binding graph. It exposes bounded source type, status, lineage, checksum, as-of,
and synthetic-state metadata without secrets or local storage paths.

## 23. Citation appendix

The Citation appendix lists only validated Citation bindings with stable labels
and exact immutable document-version anchors. A Citation invalidated by the
deterministic verifier cannot enter the appendix.

## 24. Runtime Reflection

Runtime Reflection is a deterministic rules engine, not a model. It executes at
most two rounds, reads a fixed report and binding graph, writes an immutable Run
and Findings, and cannot invoke Tools, network, create evidence, or mutate reports.

## 25. Finding

Findings use a fixed code, severity, evidence location, remediation class, and
status. They cover missing or invalid bindings, status disclosure, checksum and
reference consistency, unsafe content, Synthetic leakage, unsupported claims, and
release blockers.

## 26. Revision

Exactly one deterministic Revision round is allowed. It may delete, downgrade,
reclassify, disclose, reorder reference labels, or truncate unsafe excerpts. It
cannot create facts, Claims, Evidence, Citations, calculations, retrieval results,
or favorable conclusions.

## 27. Release Gate

The deterministic Gate runs only after Round 2. `PUBLISHABLE` means eligible for
internal controlled use and requires a content-identical sealed version with all
mandatory checks passing. It does not mean public publication, investment advice,
or a complete real-company report.

## 28. Idempotency

Identical package, manifest, policy, template, locale, renderer version, and
catalog version reuse the same Generation result. Reflection, Revision, and Gate
keys are deterministic; terminal records are immutable and duplicate concurrent
writes are constrained.

## 29. Fixtures and LF

Stage 8 fixtures and Golden artifacts use repository-enforced LF endings and
byte-based SHA-256 checksums. The neutral fixture is explicitly
`SYNTHETIC_TEST_ONLY`, `NOT_COMPANY_EVIDENCE`, `OFFLINE`, and `NOT_LIVE`.
Cross-platform checksum tests pass and no fixture is described as Live evidence.

## 30. Tools

Ten report query Tools read persisted report, section, block, Claim binding,
Evidence binding, Citation binding, Reflection Run/Finding, Revision, and Release
Gate data. All are `READ_ONLY`, `writes=false`, and `requires_network=false`.
They do not generate, reflect, revise, release, refresh, calculate, or call a model.

## 31. API

The existing API prefix exposes ten report GET-only routes. Bounded pagination,
UUID validation, stable schemas, safe 404/422 behavior, and `X-Request-ID` are
tested. There is no report POST, PUT, PATCH, or DELETE route, and responses exclude
SQL, credentials, stack traces, and local storage paths.

## 32. CLI

Explicit CLI operations cover Policy/Reflection Policy/template seed and list,
generate, reflect, revise, release-check, read views, and verified Markdown export.
The production CLI uses the SQLAlchemy composition root and transactions. It does
not implicitly network, refresh, select “latest,” parse, index, embed, recalculate,
or call a model.

## 33. Industrial FII result

For Industrial FII (`601138.SH`), identity and Snapshot binding are available but
approved company-body evidence and sufficient verified financial facts are not.
The real-company report remains `PARTIAL` or `BLOCKED`, never complete or
PUBLISHABLE. It contains only supported data-quality and limitation material and
does not use Synthetic evidence.

## 34. Micron result

For Micron (`MU`), SEC filing metadata is not treated as 10-K, 10-Q, or 8-K body
evidence. With no approved filing body and insufficient verified financial facts,
the real-company report remains `PARTIAL` or `BLOCKED`. It contains no invented
HBM, inventory-cycle, data-center, outlook, or risk-factor conclusion.

## 35. Synthetic result

The neutral Synthetic flow can reach internal `PUBLISHABLE` to verify the complete
engineering lifecycle. Its report visibly carries
`SYNTHETIC_TEST_ONLY NOT_COMPANY_EVIDENCE OFFLINE NOT_LIVE`; it cannot bind to
Industrial FII or Micron and is not production research validation.

## 36. Narrative Provider status

Production Narrative Provider: `BLOCKED`. The only production renderer is
deterministic. Test-scripted providers remain test-only; no OpenAI, Anthropic,
Gemini, or local model was enabled or called.

## 37. Reflection Provider status

Production Reflection Provider: `BLOCKED`. Production Reflection is the
deterministic rules engine. A provider cannot mark a report releasable, repair a
binding, create evidence, or become enabled from ambient environment variables.

## 38. Live Provider status

Tushare Live: `BLOCKED`; Licensed U.S. EOD: `BLOCKED`; SEC Archive Live:
`BLOCKED`; production Embedding: `BLOCKED`. Offline fixtures are not substitutes
for Live validation, and no blocked provider is reported as passed.

## 39. Database migration

Migration `0007_create_verifiable_reports_and_reflection.py` has revision
`0007_verifiable_reports`. The verified sequence was:
`0007 → downgrade -1 → 0006 → upgrade head → 0007`.
The final state is `0007_verifiable_reports (head)`.

## 40. PostgreSQL integration

PostgreSQL 17.10 development validation found 71 tables: all 15 Stage 8 tables and
56 pre-Stage 8 tables. Stage 8 migration, model, repository, lifecycle,
transaction, immutability, indexes, constraints, binding persistence, downgrade,
and re-upgrade tests pass against PostgreSQL rather than SQLite.

## 41. Ruff

`uv run ruff check .` passed with exit code 0.

## 42. Format check

`uv run ruff format --check .` passed: 406 files were already formatted.

## 43. mypy

`uv run mypy src` passed: no issues in 198 source files.

## 44. Actual pytest count

The final full regression collected **2028 collected** tests and reported
**2028 passed** in 556.70 seconds (0:09:16). This includes the two
implementation-report contract tests.

## 45. Failures, errors, skips, and warnings

The accepted final run recorded **0 failed**, **0 errors**, **0 skipped**, and
**0 warnings** under `-W error`. An earlier development run found five stale
exact-inventory assertions; these were reproduced, updated only for approved
Stage 8 modules/tables/docs/Tools, and the entire suite was rerun successfully.
One rejected final-gate invocation omitted the documented database environment and
therefore produced 237 skips plus four missing-configuration setup errors; it was
not treated as an acceptance result. The corrected independent run loaded the
documented development/test configuration without printing it and passed all 2028
tests.

## 46. Development Reflection Round 1

Round 1 reviewed report architecture, financial research, Citation/Evidence,
runtime Reflection, Revision, Release Gate, security, PostgreSQL, fixtures, and
test reliability. It recorded ten findings, including four HIGH findings. All
CRITICAL and HIGH findings were fixed.

## 47. Development Reflection Round 2

Round 2 rechecked 36 release boundaries with actual focused tests. It confirmed
atomic bindings, production composition, deterministic two-round Reflection and
one-round Revision, internal-only Gate semantics, real-company degradation,
Synthetic isolation, PostgreSQL behavior, and provider/network restrictions.

## 48. Fixed findings

Fixes include atomic factual binding persistence, full Claim/Evidence/Citation
graph validation, production Claim index and Evidence appendix composition,
deterministic binding rebasing across Revision/sealing, appendix parser correction,
explicit Synthetic rendering markers, independent Synthetic test construction,
the real SQLAlchemy CLI composition root, and updated Stage 8 regression
inventories.

## 49. Unresolved findings

No CRITICAL or HIGH engineering finding remains. Evidentiary and provider
limitations remain open conditions, not hidden passes.

## 50. BLOCKED items

Complete Industrial FII research, complete Micron research, production Narrative,
production model Reflection, Tushare Live, Licensed U.S. EOD, SEC Archive Live,
and production Embedding remain `BLOCKED`. Public publication is not implemented
or authorized.

## 51. CRITICAL and HIGH risk

Unresolved CRITICAL: `0`.

Unresolved HIGH: `0`.

The remaining material risk is misuse of a technically valid internal artifact as
complete real-company research despite missing evidence; explicit statuses,
bindings, markers, and Gate semantics mitigate but do not remove that governance
responsibility.

## 52. Current limitations

The system cannot create evidence that does not exist, cannot use SEC metadata as
filing body text, cannot infer missing financial facts, cannot validate production
model quality, and cannot claim Live-source coverage. `PUBLISHABLE` is an internal
engineering status only.

## 53. Rollback

After verifying the target database, run `uv run alembic downgrade -1` with the
approved development URL. This removes only Stage 8 triggers, functions, indexes,
and tables; Stage 2–7 objects remain. Reapply with
`uv run alembic upgrade head`. Git rollback remains a user-selected branch action.

## 54. Git status

The working branch is preserved. Task 49 is committed; the final measured test
counts and completion ledger are included in the Task 50 implementation commit.
The branch is clean after that commit. No merge, push, remote configuration, Draft
PR, or Stage 9 change has occurred.

## 55. Stage 9 authorization

Stage 9 is not authorized. Stage 8 engineering completion alone does not grant
permission to start it, use models, acquire data, publish a report, or merge this
branch.

## 56. Stage 9 allowed scope

No Stage 9 scope is currently allowed. Its permitted scope must come from a new,
explicit user prompt after Stage 8 review and the user's chosen branch-finishing
action.

## 57. Stage 9 prohibited scope

Until explicit authorization, all Stage 9 implementation is prohibited, including
model-enabled narrative/reflection, new Live-provider work, public distribution,
PDF/frontend delivery, MCP, investment recommendations, target prices, broker
connections, and trading.
