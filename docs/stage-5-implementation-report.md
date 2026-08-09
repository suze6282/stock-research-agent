# Stage 5 Implementation Report

## 1. Stage conclusion

**CONDITIONAL GO.** Canonical concepts, exact mapping boundary, periods, Decimal
normalization, as-of/restatement selection, A-share split, both TTM methods, 23
versioned formulas, immutable calculations/lineage, six read-only Tools, API, CLI,
PostgreSQL and all quality gates pass. Authorized Live numeric evidence and reviewed
production mappings remain `BLOCKED`, so neither sample is misrepresented as complete.

## 2. Current branch

`stage-5/financial-normalization`; not merged into `main`.

## 3. Implemented scope

Four-layer raw/mapping/canonical/calculation boundary; reference seed; period/unit/
currency/restatement/as-of rules; cumulative and TTM derivations; deterministic
formulas and quality states; immutable/idempotent runs; lineage; read-only query
surfaces; explicit write CLI; migration, tests and documentation.

## 4. Unimplemented scope

No new/Live provider, credential, filing-body parser, FX conversion, estimate, annualized
quarter shortcut, narrative research, target price, RAG/vector search, model call,
Agent, Reflection runtime, MCP Server, frontend, broker or trading feature.

## 5. Concept inventory

35 codes: `REVENUE`, `COST_OF_REVENUE`, `GROSS_PROFIT`, `OPERATING_INCOME`,
`EBITDA`, `PRETAX_INCOME`, `INCOME_TAX_EXPENSE`, `NET_INCOME`,
`NET_INCOME_ATTRIBUTABLE_TO_PARENT`, `BASIC_EPS`, `DILUTED_EPS`,
`CASH_AND_CASH_EQUIVALENTS`, `SHORT_TERM_INVESTMENTS`, `ACCOUNTS_RECEIVABLE`,
`INVENTORY`, `TOTAL_CURRENT_ASSETS`, `TOTAL_ASSETS`, `SHORT_TERM_DEBT`,
`LONG_TERM_DEBT`, `TOTAL_DEBT`, `TOTAL_CURRENT_LIABILITIES`, `TOTAL_LIABILITIES`,
`TOTAL_EQUITY`, `EQUITY_ATTRIBUTABLE_TO_PARENT`, `MINORITY_INTEREST`,
`PREFERRED_EQUITY`, `OPERATING_CASH_FLOW`, `CAPITAL_EXPENDITURES`,
`INVESTING_CASH_FLOW`, `FINANCING_CASH_FLOW`, `CASH_DIVIDENDS_PAID`,
`SHARE_REPURCHASES`, `BASIC_WEIGHTED_AVERAGE_SHARES`,
`DILUTED_WEIGHTED_AVERAGE_SHARES`, `PERIOD_END_SHARES_OUTSTANDING`.

## 6. Mapping inventory

The production V0.1 seed intentionally adds zero provider mappings. Test-only exact
rules cover a synthetic provider and never enter production seed/fixtures.

## 7. Mapping status

`APPROVED`, `AMBIGUOUS`, `UNMAPPED`, `DEPRECATED`. Only exact, in-validity,
evidence-reviewed APPROVED rules normalize; all other raw facts remain preserved.

## 8. Data model

Canonical concept and mapping reference data; snapshot-bound periods/facts and
derived-fact inputs; formulas; calculation runs, inputs and derived metrics.

## 9. Tables and relationships

Nine tables: `canonical_financial_concepts`, `provider_fact_mappings`,
`financial_periods`, `normalized_financial_facts`, `normalized_fact_inputs`,
`formula_definitions`, `calculation_runs`, `calculation_inputs`, `derived_metrics`.
All point back through restrictive FKs to Stage 3 securities and Stage 4 snapshots/raw
facts; no raw evidence is copied over or deleted.

## 10. Constraints

Named PK/FK/UNIQUE/CHECK constraints cover stable codes, controlled states, semantic
versions, validity/date shapes, period flags, finite `NUMERIC(38,18)`, scale > 0,
currency/unit shape, no self-lineage, idempotency and terminal status. PostgreSQL
triggers protect reference, normalized and terminal calculation records.

## 11. Indexes and purpose

- Exact mapping index: provider/concept/taxonomy/statement/form/status lookup.
- Period index: security/snapshot/end bounded period reads.
- Fact indexes: snapshot/concept/period calculation selection and source lineage.
- Run index and unique key: security/snapshot reads and input/version idempotency.
- Input/metric indexes: run+metric detail and stable lineage retrieval.

## 12. Unit strategy

Decimal-only ONE/THOUSAND/MILLION/BILLION/PER_SHARE/SHARES/PERCENT/RATIO; original
value/unit, exact scale and normalized value/unit are retained. Unknown/incompatible
units block; no early rounding.

## 13. Currency strategy

Currency is explicit and preserved. Same-basis formulas reject missing/mixed currency.
There is no implicit FX, rate lookup or currency conversion.

## 14. Restatement strategy

Raw/restated versions coexist. Only versions published by the snapshot cutoff are
eligible; ambiguous conflicts block. Old snapshots and runs remain immutable.

## 15. as-of strategy

Require known `source_published_at <= research_as_of_time`; retrieval time never
substitutes. Stable ordering/checksums make replay deterministic and leakage tests pass.

## 16. A-share cumulative split

Versioned Q1, H1-Q1, 9M-H1 and FY-9M operations require matching security, concept,
year, unit, currency and accounting basis. Reported cumulative facts remain and
derived quarters record ordered input IDs. Instant/EPS/weighted shares are blocked.

## 17. U.S. fiscal year

Source FY/FP/start/end/form and actual durations drive period identity. Non-calendar
and 52/53-week years remain visible. 10-K stays annual; Q4 requires comparable FY-9M.

## 18. TTM

Method A sums four comparable consecutive single quarters. Method B uses latest FY +
latest YTD - prior comparable YTD. Persisted metric periods identify
`TTM:FOUR_QUARTERS` or `TTM:ANNUAL_YTD_BRIDGE`, and CalculationInputs retain roles.
No annual fact or annualized quarter is mislabeled TTM.

## 19. Formula Registry

23 whitelisted deterministic implementations; text expressions are audit metadata,
never evaluated. Every definition records inputs, period/currency/denominator/sign
policy and lifecycle state.

## 20. Formula version

V0.1 formulas use immutable `1.0.0`; calculation/formula set/mapping/normalization
versions and input checksum bind every run.

## 21. Metric inventory

Revenue growth; gross/operating/parent-net margins; ROE/ROA/ROIC; OCF/FCF;
liabilities/assets; net debt; basic/diluted EPS; revenue/parent-net-income/EBITDA TTM.

## 22. Valuation metric inventory

Market cap, PE TTM diluted, PB parent, PS TTM, enterprise value, EV/EBITDA TTM and
FCF yield TTM. Golden formulas pass; sample numeric valuation remains blocked by
missing verified financial/share facts.

## 23. N/M rules

Nonpositive valuation denominators and nonpositive average capital/equity conditions
return `NOT_MEANINGFUL` without a number. Missing inputs return `NULL/BLOCKED`; actual
zero returns `ZERO`. Negative valid flows/margins remain numeric with warnings.

## 24. Lineage

RawPayload → ProviderFinancialFact → ProviderFactMapping → NormalizedFinancialFact →
FormulaDefinition → CalculationInput → DerivedMetric → CalculationRun. Derived
cumulative facts also retain NormalizedFactInput rows.

## 25. Tool inventory

`get_normalized_financial_facts`, `get_financial_periods`,
`get_financial_metrics`, `get_metric_detail`, `get_metric_lineage`,
`get_calculation_run`; all v1.0.0, READ_ONLY, writes=false, network=false.

## 26. API

Six bounded GET-only routes for periods, normalized facts, metrics/detail and
calculation run/lineage. Invalid input is 422, missing resources 404, valid
PARTIAL/BLOCKED outcomes HTTP 200. Request ID/safe error/OpenAPI contracts pass.

## 27. CLI

Explicit writes: `financials seed-v0|normalize|calculate`. Reads:
`periods|facts|metrics|metric|lineage`. Human/JSON output and deterministic nonzero
BLOCKED exit behavior were executed. No read triggers refresh/network.

## 28. Industrial FII result

Snapshot `f4e25332-28b2-40e3-8f9d-2348069ceb7d`: 0 raw financial facts, normalization
BLOCKED, 0 periods/facts. Calculation run `afd18363-7189-4a6b-aeb9-4f1747ab2d30`:
23 BLOCKED/NULL metrics, 23 warnings, empty-input SHA-256 `e3b0c442…b855`; replay reused
the run. Evidence remains FIXTURE/OFFLINE/NOT_LIVE.

## 29. Micron result

Snapshot `c0f7e785-b9dc-4eab-937d-53f99f27693f`: 0 raw financial facts,
normalization BLOCKED, 0 periods/facts. Run `1ad3fca4-5f37-4b08-9ba4-d62d3683d1c0`:
23 BLOCKED/NULL metrics, 23 warnings, the same deterministic empty checksum; replay
reused it. API/CLI provenance is FIXTURE/OFFLINE/NOT_LIVE.

## 30. Metrics that cannot be calculated and why

All 23 sample metrics: neither approved sample snapshot contains a numeric financial
fact. Valuation additionally lacks verified shares/earnings/balance inputs. Missing
evidence is not replaced by zero, empty text, estimate or invented fixture data.

## 31. Golden Test result

PASS for A-share split; four-quarter and bridge TTM; margins; ROE/ROA/ROIC; OCF/FCF;
net debt; EPS; market cap; PE/PB/PS/EV/EV-EBITDA/FCF yield; unit/currency; precision;
NULL/N/M/ZERO and restatement/as-of counterexamples.

## 32. Fixture limitations

Stage 1-derived crops are real safe slices but not Live. FII provides one price row;
MU provides one price row and three filing metadata rows. Neither has numeric facts.

## 33. Live source BLOCKED status

`TUSHARE_PRO`: missing token/cache permission. `LICENSED_US_EOD`: missing named
provider/key/license. `SEC_ARCHIVES`: missing contact/User-Agent. Separate test:
three explained skips, HTTP NOT_ATTEMPTED, no payload/snapshot.

## 34. Database migration

Development and isolated test DB both completed upgrade head → downgrade -1 → upgrade
head, ending at `0004_financial_normalization`. Downgrade removes only Stage 5.

## 35. PostgreSQL integration

PASS for catalog, constraints/indexes/triggers, migration replay, seed idempotency,
raw preservation, exact mapped calculation, immutable terminal data, transaction
rollback, concurrent one-run reuse and isolation. SQLite was not used as evidence.

## 36. Ruff

`uv run ruff check .`: All checks passed, exit 0.

## 37. Format check

`uv run ruff format --check .`: 166 files already formatted, exit 0.

## 38. mypy

`uv run mypy src`: no issues in 94 source files, exit 0.

## 39. Actual pytest count and result

`uv run pytest -W error`: **1115 passed in 199.83s**, 0 warnings, 0 default skips,
exit 0.

## 40. New test categories

145 Stage 5 cases: 136 unit/golden/contract/document cases plus 9 real-PostgreSQL
migration/repository cases. Parameterization enumerates real concept/unit/formula and
negative contracts; there are no empty parameter sets.

## 41. Skipped tests

Default: zero. Separate `live_tests`: exactly three explained BLOCKED skips for
Tushare, licensed U.S. EOD and SEC Archive; all report HTTP NOT_ATTEMPTED.

## 42. Reflection Round 1

Five HIGH defects were fixed: fact identity, concurrent run race, fixture provenance,
safe missing-resource API semantics and persisted bridge TTM. Open items are MEDIUM/
LOW external evidence/production hardening. Unresolved CRITICAL/HIGH: zero.

## 43. Reflection Round 2

All 40 checks pass. Three MEDIUM documentation/progression assertions were fixed after
actual command/full-suite failures. Unresolved CRITICAL/HIGH: zero.

## 44. Fixed issues

Unique fact/period identities; exact blocked output units; advisory-lock concurrency;
fixture provenance; warning deduplication; API 404; both persisted TTM methods; correct
CLI docs; Stage 5 Tool and migration progression expectations.

## 45. Unresolved issues

Acquire licensed/authorized numeric evidence and reviewer-approved production mappings;
validate sample valuation lineage with real shares; conduct production security review.

## 46. CRITICAL/HIGH risk

Unresolved `CRITICAL=0`, `HIGH=0`. External Live/evidence blockers prevent a GO claim
but are not disguised implementation success.

## 47. Current limitations

Two securities, offline evidence, no production mappings/numeric sample facts, no FX,
no narrative/recommendation/target price and none of the prohibited Stage 6/runtime
features.

## 48. Rollback

Back up non-fixture Stage 5 data, verify the target, then downgrade one revision to
`0003_data_access_snapshots`. This removes Stage 5 objects only. Re-upgrade and rerun
`financials seed-v0`; never overwrite raw Stage 4 evidence or rewrite Git history.

## 49. Git status

Feature branch only; Stage 5 code, tests, documentation, Reflections and report are
committed and the worktree is clean. No merge, push or branch deletion is authorized.

## 50. Whether Stage 6 entry criteria are met

The Stage 5 offline architecture is complete under `CONDITIONAL GO`, but Stage 6 may
begin only after the user explicitly supplies and approves its scope. It has not begun.

## 51. Stage 6 allowed scope

No Stage 6 specification was supplied in this task. Only planning, preflight and work
explicitly authorized by a future Stage 6 prompt are allowed.

## 52. Stage 6 forbidden scope

Until explicit authorization: no RAG/vector store, document-body parsing, model/Agent/
Reflection runtime, MCP Server, narrative report, target price, frontend, broker or
trading implementation; no Live credentials or external calls may be inferred.
