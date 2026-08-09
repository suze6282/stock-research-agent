# Stage 5 Financial Normalization Implementation Plan

> Stage gate: implement only financial normalization, period semantics, and a
> deterministic calculation/query layer. Do not begin Stage 6. Every production
> change follows an observed failing test, the smallest implementation, and a
> passing targeted test before the next slice.

## 1. Stage objective

- [ ] Convert eligible Stage 4 `ProviderFinancialFact` evidence into versioned,
  traceable canonical facts without changing raw evidence.
- [ ] Model fiscal periods explicitly for A-share cumulative reporting and U.S.
  non-calendar/52-week/53-week reporting.
- [ ] Calculate TTM, operating metrics, returns and basic valuation metrics with
  deterministic Decimal arithmetic and versioned formulas.
- [ ] Persist immutable, idempotent calculation runs, their inputs, warnings and
  derived outputs bound to a Stage 4 snapshot.
- [ ] Expose the same bounded read-only query services through Tool, API and CLI.
- [ ] Demonstrate honest `PARTIAL`/`BLOCKED` sample behavior because the approved
  Stage 4 fixtures contain no numeric financial facts.

## 2. Allowed scope

- [ ] Canonical financial concepts and versioned provider mappings.
- [ ] Financial periods, normalized facts, units, restatements and as-of selection.
- [ ] A-share cumulative de-accumulation and U.S. fiscal-period validation.
- [ ] Deterministic TTM and V0.1 metric/formula registry.
- [ ] Calculation run/input/metric lineage, seed, repository, migration and tests.
- [ ] Explicit normalization/calculation CLI writes and read-only Tool/API/CLI reads.
- [ ] Industrial FII and Micron offline-fixture acceptance without invented facts.
- [ ] Documentation, two bounded Reflection rounds and a Stage 5 report.

## 3. Forbidden scope

- [ ] Do not add or qualify a Live provider, credentials, network calls or new fixture
  facts; `TUSHARE_PRO`, licensed U.S. EOD and `SEC_ARCHIVES` remain `BLOCKED`.
- [ ] Do not parse filing/PDF/document bodies or promote extracted tables.
- [ ] Do not use float, implicit FX conversion, live exchange rates, estimates,
  zero-fill, fuzzy mapping, LLM mapping, arbitrary `eval`, or user-supplied code.
- [ ] Do not implement narrative reports, scenarios, target prices, RAG/vector search,
  model calls, Agent loops, Reflection runtime, MCP Server, frontend, broker or trading.
- [ ] Do not implement or enter Stage 6 and do not merge this branch to `main`.

## 4. Raw data input

- [ ] Consume only persisted Stage 4 `provider_financial_facts` selected through a
  persisted immutable `data_snapshot` and its `snapshot_items`.
- [ ] Treat `ProviderFinancialFact` and its payload as immutable evidence; retain
  provider, payload, source fact, dates, unit, currency, taxonomy/context and checksum.
- [ ] Reject facts absent from the snapshot or published after
  `research_as_of_time`; never substitute `retrieved_at` for publication time.
- [ ] Preserve unmapped and ambiguous raw facts in the raw layer with warnings.
- [ ] Default test execution remains offline and fixtures remain
  `FIXTURE/OFFLINE/NOT_LIVE` in all surfaces.

## 5. Canonical Concept design

- [ ] Add `domain/financials/concepts.py` with the 35 stable concept codes specified
  by the Stage 5 contract across income statement, balance sheet, cash flow, shares
  and per-share data.
- [ ] Record statement type, fact nature, permitted period shape, unit type,
  cumulative/TTM support, negative-value policy, description, version and status.
- [ ] Keep parent-attributable versus total income, basic versus diluted EPS, and
  period-end versus weighted-average shares distinct.
- [ ] Add an idempotent versioned concept seed; deprecated concepts cannot receive
  new default mappings.

## 6. Fact Mapping design

- [ ] Add exact, provider/taxonomy-specific `ProviderFactMapping` rules with mapping
  version, statement/form/context/dimension filters, validity range and review source.
- [ ] Match exact provider concept before other declared dimensions; never use label
  similarity, fuzzy matching or an LLM.
- [ ] Return `APPROVED`, `AMBIGUOUS`, `UNMAPPED` or `DEPRECATED` deterministically.
- [ ] Require source/review evidence for APPROVED mappings and preserve old versions.
- [ ] Keep production seed rules separate from synthetic test-only mappings.

## 7. Financial period design

- [ ] Add typed period schemas and a `financial_periods` table bound to security and
  snapshot with fiscal year/quarter/period, explicit type, start/end, filing and
  publication timestamps, duration days, cumulative/single-quarter/TTM flags,
  accounting standard and form type.
- [ ] Distinguish duration, instant, annual, quarter, half-year, nine-month YTD,
  generic YTD and TTM; do not infer publication time from period/filing dates.
- [ ] Validate date order and compute actual duration days, preserving 52/53-week years.
- [ ] Return `PARTIAL`/`BLOCKED` when fiscal identity or comparable duration is unknown.

## 8. Unit and currency strategy

- [ ] Add `UnitNormalizationPolicy` for ONE, THOUSAND, MILLION, BILLION, PER_SHARE,
  SHARES, PERCENT and RATIO using `Decimal` only.
- [ ] Store original value/unit, normalized value/unit and exact scale factor; retain
  full internal precision and round only for display.
- [ ] Block unknown units and incompatible amount/share/per-share/percent combinations.
- [ ] Do not guess Chinese or U.S. scale notation and do not convert currencies.
- [ ] Block valuation when price and financial currency differ.

## 9. Financial restatement strategy

- [ ] Preserve original, amended and restated versions instead of overwriting facts.
- [ ] Select only versions visible at snapshot cutoff and bind every calculation to
  the exact normalized fact IDs used.
- [ ] Allow later snapshots to select later corrections while old snapshots replay.
- [ ] Emit a conflict warning and avoid silent latest-value selection when validity
  cannot be resolved; derive `is_restated` only from evidence or an explicit rule.

## 10. as-of selection strategy

- [ ] Filter raw facts and versions by `source_published_at <= research_as_of_time`.
- [ ] Unknown publication time yields warning and prevents an unqualified PASS.
- [ ] Use stable ordering and bounded queries; same database state/cutoff/version
  returns the same selected IDs.
- [ ] Add leakage tests where a later restatement is invisible to an earlier snapshot.

## 11. A-share cumulative-value handling

- [ ] Implement versioned Q1, H1-Q1, 9M-H1 and FY-9M de-accumulation for eligible
  duration facts only.
- [ ] Require same security, concept, fiscal year, currency, unit, accounting basis,
  continuous periods, cumulative flags, cutoff eligibility and conflict-free versions.
- [ ] Retain cumulative facts and create separate derived single-quarter facts with
  every input fact ID, formula version and `is_derived_from_cumulative=true`.
- [ ] Block missing predecessors or basis changes; warn rather than reject a valid
  negative difference.
- [ ] Never de-accumulate instant facts, EPS by default, or weighted-average shares.

## 12. U.S. fiscal-year handling

- [ ] Use source FY/FP/start/end/form/context rather than calendar-year inference.
- [ ] Support non-calendar years, 52/53-week years, 10-K, 10-Q, YTD and single-quarter
  contexts with actual duration checks.
- [ ] Require explicit mapping for custom XBRL taxonomy concepts.
- [ ] Do not treat 10-K as Q4; FY-9M derivation must satisfy the same comparability rules.

## 13. TTM algorithm

- [ ] Implement method A: sum the latest four comparable single-quarter duration facts.
- [ ] Implement method B: latest FY + latest YTD - prior-year comparable YTD only when
  concept, currency, unit, basis and duration are compatible.
- [ ] Store method, formula version and all four-quarter or three-bridge input IDs.
- [ ] Block instant/balance-sheet TTM, missing quarters and invalid EPS treatment; do
  not annualize a quarter or relabel a latest annual fact as TTM.
- [ ] Warn on 53-week or materially non-comparable durations and prove stable replay.

## 14. Formula Registry

- [ ] Add immutable `FormulaDefinition` versions for the exact formulas in
  `docs/metric-definitions-v0.1.md`; no dynamic `eval` or arbitrary function/field access.
- [ ] Register Revenue Growth, Gross/Operating/Parent Net Margin, ROE, ROA, ROIC, OCF,
  FCF, Debt Ratio, Net Debt, Basic/Diluted EPS, Market Cap, PE, PB, PS, EV, EV/EBITDA
  and FCF Yield with typed input roles and denominator/negative policies.
- [ ] V0.1 Net Debt subtracts cash and cash equivalents only; short-term investments
  remain an optional future formula-version input, matching the accepted metric document.
- [ ] Gross margin uses reported gross profit only when it reconciles; otherwise use
  revenue minus cost of revenue and record the selected deterministic input path.
- [ ] Keep formula code and documentation version-locked and cover each core formula
  with unit and golden tests.

## 15. Calculation Run

- [ ] Add `calculation_runs`, `calculation_inputs` and `derived_metrics` with security,
  snapshot, version set, status, timestamps, warnings/errors and exact Decimal inputs.
- [ ] Statuses are RUNNING/PASS/PARTIAL/BLOCKED/FAIL; terminal runs are immutable in
  repository logic and PostgreSQL triggers.
- [ ] Compute an idempotency/input checksum so identical snapshot and versions reuse a
  terminal run; changed facts/mappings/formulas create a new run.
- [ ] Never persist a fake numeric value for BLOCKED, NULL or N/M results.

## 16. Metric lineage

- [ ] Every metric references its calculation run, security, snapshot, period,
  formula version, quality state and warning codes.
- [ ] Every numeric metric has ordered `CalculationInput` records with normalized fact
  IDs, input role and exact value used; market-price inputs retain source record lineage.
- [ ] Expose the full raw fact -> mapping -> normalized fact -> formula -> metric chain.
- [ ] Preserve old formula/mapping/normalization versions for historical replay.

## 17. Data quality status

- [ ] Define exact PASS/PARTIAL/BLOCKED/FAIL plus value-state semantics for VALUE,
  ZERO, NULL and NOT_MEANINGFUL (N/M), without pseudo-confidence scores.
- [ ] Use zero only when the actual fact/calculation is exactly zero; never as a fill.
- [ ] Treat missing numerator/input as NULL/BLOCKED and invalid/nonpositive valuation
  denominator as N/M with no numeric value.
- [ ] Keep warnings structured, stable, bounded and safe for logs/API/CLI.

## 18. Tool

- [ ] Register exactly the six Stage 5 read-only tools with stable versions:
  `get_normalized_financial_facts`, `get_financial_periods`,
  `get_financial_metrics`, `get_metric_detail`, `get_metric_lineage`,
  `get_calculation_run`.
- [ ] Mark all `READ_ONLY`, `writes=false`, `requires_network=false`; reuse one query
  service and never normalize, calculate, ingest, refresh or download implicitly.
- [ ] Use bounded inputs/results and stable JSON-compatible schemas with provenance.

## 19. API

- [ ] Add Stage 5 GET routes under the existing `/api/v1` root for normalized facts,
  periods, metrics, metric detail/lineage and calculation runs.
- [ ] Reuse request IDs, database lifecycle and safe error envelopes; invalid input is
  422, missing resources 404, business PARTIAL/BLOCKED remains a typed response.
- [ ] Keep API read-only, bounded and offline; never expose SQL, paths, credentials,
  raw exceptions or an endpoint that triggers normalization/calculation.

## 20. CLI

- [ ] Add explicit write commands to seed concepts/mappings, normalize one snapshot
  and calculate one snapshot; all mutations require an explicit command.
- [ ] Add human and `--json` read commands for facts, periods, metrics, detail, lineage
  and runs using the same services as Tool/API.
- [ ] Give PARTIAL/BLOCKED/invalid/not-found deterministic non-zero exit codes and
  prove help/output/offline behavior with subprocess tests.

## 21. Database migration

- [ ] Create `0004_create_financial_normalization_and_metrics` with canonical concepts,
  provider mappings, periods, normalized facts, formula definitions, calculation runs,
  inputs, derived metrics and any necessary lineage association.
- [ ] Use SQLAlchemy 2.x typed models, UUID PKs, UTC timestamps, restrictive foreign
  keys, named UNIQUE/CHECK constraints and indexes tied to real queries.
- [ ] Add indexes for concept/mapping lookup, snapshot-period selection, normalized
  fact uniqueness/as-of paths, run idempotency and metric/lineage queries.
- [ ] Keep business seeds out of Alembic and implement a complete downgrade without
  deleting Stage 1-4 tables.
- [ ] Verify development `upgrade -> downgrade -1 -> upgrade` and isolated
  `base -> 0001 -> 0002 -> 0003 -> 0004 -> downgrade -1 -> upgrade`.

## 22. Test matrix and TDD sequence

- [ ] Slice A RED/GREEN: concept registry, controlled enums and exact provider mapping.
- [ ] Slice B RED/GREEN: Decimal unit scaling, percent semantics and currency blocking.
- [ ] Slice C RED/GREEN: dates, duration/instant, non-calendar and 52/53-week periods.
- [ ] Slice D RED/GREEN: restatement and as-of selection with future-leakage negatives.
- [ ] Slice E RED/GREEN: A-share Q1/H1/9M/FY split and rejected invalid splits.
- [ ] Slice F RED/GREEN: four-quarter and bridge TTM with duration/comparability checks.
- [ ] Slice G RED/GREEN: all required metrics, N/M/NULL/0 and Decimal precision.
- [ ] Slice H RED/GREEN: SQLAlchemy models, migration catalog, constraints, rollback,
  immutable terminal runs, idempotency, concurrency and PostgreSQL isolation.
- [ ] Slice I RED/GREEN: normalizer/calculator repositories and both honest sample cases.
- [ ] Slice J RED/GREEN: Tool Registry/permissions, API contracts and CLI contracts.
- [ ] Golden cases include A-share split; four-quarter and bridge TTM; gross/operating/
  net margins; ROE/ROA/FCF/net debt; valuation N/M; EV; units; precision; restatement.
- [ ] Run targeted tests after every RED/GREEN slice, then `uv sync`, Ruff, format,
  mypy and full `pytest -W error`; no default network, skips, warnings or weak tests.

## 23. Reflection

- [ ] Round 1: six-role review by accounting/data, equity research, financial model,
  database/architecture, Tool/Agent boundary, and security/reliability perspectives.
- [ ] Record ID, role, severity, description, evidence, affected files, fix, blocker and
  status for every finding; fix all CRITICAL/HIGH before proceeding.
- [ ] Round 2: rerun the prompt's full consistency, reproducibility, migration,
  sample, lineage, boundary and quality checklist with actual commands/evidence.
- [ ] Fix all CRITICAL/HIGH findings and report lower-severity residuals honestly.

## 24. Acceptance criteria

- [ ] Work exists only on `stage-5/financial-normalization` with no unrelated changes.
- [ ] Four-layer boundary, canonical facts, periods, mappings, units, corrections,
  cumulative split, TTM, formulas, immutable lineage and quality semantics pass.
- [ ] Both sample snapshots produce no invented normalized amounts or metrics and
  return explicit missing-evidence `PARTIAL`/`BLOCKED` warnings.
- [ ] Six read-only Tools, read-only API and CLI contracts pass without implicit work.
- [ ] PostgreSQL, migration cycle, concurrency, Ruff, format, mypy and complete pytest
  all exit 0 with zero warnings and no unexplained skips.
- [ ] Two Reflection rounds have zero unresolved CRITICAL/HIGH issues.
- [ ] Stage report uses GO/CONDITIONAL GO/NO-GO based on evidence; Live blockers favor
  CONDITIONAL GO and no Stage 6 work begins.

## 25. Rollback plan

- [ ] Check for user changes before any Git operation; revert only Stage 5 commits.
- [ ] Back up non-fixture data and explicitly confirm the target database before
  `uv run alembic downgrade 0003_data_access_snapshots`.
- [ ] Downgrade removes only Stage 5 tables/triggers/indexes; Stage 1-4 schema, raw
  evidence, snapshots and blobs remain untouched.
- [ ] Re-upgrade and rerun versioned seeds; seeds never overwrite manual changes.
- [ ] Do not delete the feature branch or merge/rewrite `main` without user choice.

## Coverage self-review before production code

- [x] Provider/raw input, snapshot/as-of and restatement visibility are covered.
- [x] Canonical concepts, exact versioned mappings and unmapped/ambiguous behavior are covered.
- [x] Periods, units, currency, A-share de-accumulation and U.S. fiscal calendars are covered.
- [x] Both TTM methods, Formula Registry, calculation runs, immutable lineage and quality states are covered.
- [x] Required operating/return/cash-flow/share/valuation metrics and V0.1 metric-definition reconciliation are covered.
- [x] Database migration, constraints, indexes, seed separation, downgrade, PostgreSQL and concurrency are covered.
- [x] Explicit CLI writes, read-only Tool/API/query boundaries and offline/no-refresh behavior are covered.
- [x] Industrial FII/Micron honest missing-data acceptance and all Live blockers are covered.
- [x] Golden/unit/integration/contract/full-regression tests, two Reflection rounds, documentation and report are covered.
- [x] Every prohibited Stage 6/network/LLM/RAG/Agent/MCP/trading scope is explicitly excluded.
- [x] No prompt requirement is intentionally omitted; implementation may start with the first RED test.

## Execution checklist

- [x] Task 1: add failing concept/mapping contract tests; implement the canonical registry.
- [x] Task 2: add failing unit/period tests; implement Decimal units and fiscal periods.
- [x] Task 3: add failing as-of/restatement tests; implement deterministic fact selection.
- [x] Task 4: add failing A-share/TTM golden tests; implement period derivations.
- [x] Task 5: add failing formula golden tests; implement safe formula functions/registry.
- [x] Task 6: add failing model/migration tests; implement schema and `0004` downgrade.
- [x] Task 7: add failing repository/service tests; implement seeds, normalization and calculation runs.
- [x] Task 8: add failing immutability/idempotency/concurrency tests; enforce in PostgreSQL.
- [x] Task 9: add failing Tool/API/CLI contracts; implement six read-only query surfaces and explicit writes.
- [x] Task 10: run both sample snapshots; document exact PARTIAL/BLOCKED evidence.
- [x] Task 11: update README, financial, database, snapshot, API, Tool and testing documentation.
- [x] Task 12: complete Reflection Round 1, fix all CRITICAL/HIGH, and rerun affected tests.
- [x] Task 13: complete Reflection Round 2, migrations, full gates and implementation report.
- [x] Task 14: commit a clean feature branch and offer finishing choices without selecting one.

## Completion evidence

- [x] Development and isolated PostgreSQL migration cycles end at `0004`.
- [x] Both samples replay with honest `BLOCKED/NULL` results and no invented facts.
- [x] Six financial Tools and six API routes are read-only and offline.
- [x] Round 1 and Round 2 have zero unresolved CRITICAL/HIGH findings.
- [x] `uv sync`, Ruff, format, mypy and `1115 passed` complete with zero warnings/skips.
- [x] Live sources remain explicitly BLOCKED; Stage 6 has not started.
