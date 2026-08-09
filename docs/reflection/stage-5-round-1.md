# Stage 5 Reflection — Round 1

## Conclusion

Six-role review found five blocking defects during implementation. Each was reproduced
by a failing test and fixed before the full gate. Unresolved counts are
`CRITICAL=0`, `HIGH=0`, `MEDIUM=2`, `LOW=1`. The remaining items are external evidence
or production-hardening limits and do not justify inventing sample numbers.

## Role review

### Accounting and financial data specialist

- Parent-attributable and total income, basic/diluted EPS, weighted-average/period-end
  shares, duration/instant facts and reported/derived facts remain distinct.
- Unit scale, currency, source FY/FP, actual dates, publication time and restatement
  visibility are explicit. No retrieval-time substitution or FX conversion exists.
- A-share split and U.S. non-calendar/52/53-week behavior have positive and negative
  golden cases; 10-K is never relabeled as Q4.

### Equity research analyst

- Formula definitions and denominator policies are inspectable and versioned.
- Negative/nonpositive valuation denominators use N/M, not misleading negative
  multiples; missing evidence is NULL/BLOCKED, not zero.
- Cyclicality and accounting limitations are documented. No recommendation, target
  price or false precision is generated.

### Financial model engineer

- All financial values use Decimal/NUMERIC with no internal rounding.
- Both TTM methods validate basis/duration and persist exact input roles plus a method
  marker; average-balance formulas require opening and closing values.
- Stable checksums, terminal-run immutability, idempotent replay and concurrent reuse
  are verified.

### Database and data architect

- Nine Stage 5 tables use restrictive FKs, named checks/unique keys and focused indexes.
- Reported and de-accumulated facts have distinct identities; reference/fact/run rows
  have trigger-backed immutability.
- Isolated and development upgrade/downgrade/re-upgrade and concurrent PostgreSQL
  calculation tests pass.

### Tool Use and Agent architect

- Six financial Tools are strict, bounded, read-only, offline and reuse one query
  service across Tool/API/CLI reads.
- Normalization/calculation writes require explicit CLI/internal-service calls. A read
  cannot ingest, refresh, rebuild, download or call a model.
- Schemas are future-reusable, but no Agent, MCP Server or RAG runtime was introduced.

### Security and reliability engineer

- Formula text is audit metadata and execution is a fixed whitelist; source scan found
  no `eval`, dynamic code, financial float, network call or write API route.
- Parameterized SQLAlchemy queries, strict UUID/limit schemas, safe 404/422/503
  envelopes and request IDs prevent raw database/exception leakage.
- Fixture provenance stays `FIXTURE/OFFLINE/NOT_LIVE`; Live tests remain separately
  blocked and perform no HTTP.

## Findings

| Problem ID | Role | Severity | Description | Evidence | Affected files | Fix | Blocking | Status |
| --- | --- | --- | --- | --- | --- | --- | --- | --- |
| S5-R1-001 | Database / accounting | HIGH | Initial period/fact uniqueness collapsed reported cumulative and derived single-quarter rows. | PostgreSQL/model regression failed on valid coexistence. | Models, migration, model tests | Added cumulative/single-quarter and derived-state identity dimensions and migration coverage. | Yes | FIXED (`144f266`, `38b8dcf`) |
| S5-R1-002 | Reliability / database | HIGH | Two concurrent identical calculations could race before observing the terminal run. | New two-thread PostgreSQL test reproduced the unprotected check/create window. | Financial repository/service/integration test | Added deterministic transaction advisory lock before lookup/create; both callers now return one run and one 23-metric set. | Yes | FIXED (`323ceec`) |
| S5-R1-003 | Tool / provenance | HIGH | Persisted financial reads initially returned UNKNOWN provenance even when their snapshot items were fixture evidence. | Tool test failed expected `FIXTURE/OFFLINE/NOT_LIVE`. | Financial repository/query/Tools/tests | Derive bounded provenance from snapshot providers; deduplicate warnings. | Yes | FIXED (`323ceec`) |
| S5-R1-004 | API / security | HIGH | Missing calculation runs returned a business envelope instead of the required safe HTTP 404. | New helper/API contract failed. | `api/read_only.py`, API contract tests | Map missing snapshot/run warnings to `FINANCIAL_RESOURCE_NOT_FOUND` 404 without internal detail. | Yes | FIXED (`323ceec`) |
| S5-R1-005 | Financial model | HIGH | Domain bridge TTM existed, but the persisted calculation service only selected four quarters and did not record bridge-method lineage. | Service RED test returned NULL instead of 120 for FY 100 + YTD 60 - prior YTD 40. | Formula registry, calculation service/schemas/repository/tests | Added comparable-basis bridge fallback, stable input roles and `TTM:FOUR_QUARTERS` / `TTM:ANNUAL_YTD_BRIDGE` markers. | Yes | FIXED (`482abcd`) |
| S5-R1-006 | Data availability | MEDIUM | Both approved sample snapshots contain no numeric financial facts, so production provider mappings and numeric sample metrics cannot be validated. | Snapshot/CLI inspection: FII one price item; MU price plus three filing-metadata items; zero financial facts. | External provider/fixtures | Keep results BLOCKED/NULL; acquire authorized real facts and reviewed mappings later without rewriting fixtures. | No | OPEN |
| S5-R1-007 | Formula orchestration | MEDIUM | The persisted sample calculation cannot demonstrate price/share valuation lineage because no sample contains verified period-end shares. | Market-cap golden formula passes; sample inputs are insufficient. | External evidence and future approved mappings | Validate the existing formula/input lineage with licensed shares evidence before production use. | No | OPEN |
| S5-R1-008 | Security | LOW | Review was targeted and evidence-based, not a claim of exhaustive production penetration testing. | Scope and local-only execution. | Stage 5 branch | Run dedicated production security review before enabling Live data or public service. | No | OPEN |

## Fix verification

```text
TTM bridge RED: NULL/BLOCKED; GREEN: 120 and three persisted roles
concurrency/provenance/API/repository focused suite: 12 passed
financial migration + repository PostgreSQL suite: 9 passed
complete default suite after fixes: 1115 passed, 0 skipped, 0 warnings
```

No unresolved CRITICAL or HIGH finding remains. Stage 6 has not started.
