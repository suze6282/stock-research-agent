# Stage 5 Reflection — Round 2

## Conclusion

Round 2 rechecked all 40 required consistency and boundary items against code,
PostgreSQL, CLI/API output, migrations and the final `1115 passed` run. Three
regressions were found and fixed: one CLI documentation mismatch and two stale Stage
4 test expectations. Unresolved `CRITICAL=0`, `HIGH=0`.

## Round 2 fixes

| Problem ID | Severity | Description | Evidence | Fix | Status |
| --- | --- | --- | --- | --- | --- |
| S5-R2-001 | MEDIUM | README initially documented snapshot ID as a positional CLI argument. | Executed command exited 2 with required `--snapshot`. | Corrected README/financial docs to exact CLI help contract and added documentation tests. | FIXED |
| S5-R2-002 | MEDIUM | Old CLI integration expected eight Tool metadata rows instead of Stage 4+5's fourteen. | First full run failed `8 != 14`. | Updated the progression assertion; focused test passed. | FIXED |
| S5-R2-003 | MEDIUM | General migration regression still treated Stage 4 as Alembic head. | First full run reported nine unexpected Stage 5 tables. | Added exact Stage 5 catalog and asserted `downgrade -1` removes only Stage 5. | FIXED |

## Forty required checks

| # | Check | Result | Actual evidence |
| ---: | --- | --- | --- |
| 1 | Concept and docs agree | PASS | 35 seeded concepts; documentation contract and registry tests pass. |
| 2 | No fuzzy automatic mapping approval | PASS | Exact provider/taxonomy/form/context matcher; ambiguity/unmapped tests pass. |
| 3 | Unmapped raw facts are retained | PASS | Normalizer writes no canonical row and leaves Stage 4 source untouched. |
| 4 | Raw facts are not overwritten | PASS | PostgreSQL synthetic test compares original values after normalization/calculation. |
| 5 | Unit scaling is reproducible | PASS | Decimal value, original/normalized unit and scale factor golden tests. |
| 6 | Different currencies do not calculate | PASS | Cross-currency formula/unit tests return BLOCKED. |
| 7 | A-share cumulative split is correct | PASS | Q1/H1/9M/FY golden split and persisted lineage pass. |
| 8 | Balance sheet is not split | PASS | Instant/concept negative cases block. |
| 9 | U.S. fiscal year is not treated as calendar year | PASS | Source fiscal identity/non-calendar/52/53-week tests pass. |
| 10 | 10-K is not treated directly as Q4 | PASS | Annual period remains annual; only comparable FY-9M difference is eligible. |
| 11 | TTM does not annualize a quarter | PASS | Missing/nonconsecutive quarter tests block; both real methods have golden tests. |
| 12 | Restatement does not mutate old snapshot | PASS | Publication-cutoff leakage and version-selection tests pass. |
| 13 | Old calculation run is immutable | PASS | Repository guards and PostgreSQL triggers reject terminal mutation. |
| 14 | Formula versions are stable | PASS | 23 unique code/version seed rows and immutable reference triggers. |
| 15 | Every numeric metric has lineage | PASS | CalculationInput records exact normalized IDs/roles/values; synthetic PG test passes. |
| 16 | Negative-profit PE is N/M | PASS | Golden valuation test returns no numeric value. |
| 17 | Negative-equity PB is N/M | PASS | Denominator policy and formula tests pass. |
| 18 | Nonpositive EBITDA EV/EBITDA is N/M | PASS | Golden test returns NOT_MEANINGFUL. |
| 19 | Missing values are not filled with zero | PASS | Both samples produce 23 NULL metrics; missing-input tests distinguish ZERO. |
| 20 | No float financial calculation | PASS | Type/model/source scans and float-rejection tests pass. |
| 21 | No arbitrary eval | PASS | Whitelisted implementation registry; source scan has no eval/exec path. |
| 22 | Tools are read-only | PASS | Six Stage 5 Tools: READ_ONLY, writes=false, network=false. |
| 23 | API is read-only | PASS | Six GET paths; OpenAPI scan finds no financial POST/PUT/PATCH/DELETE. |
| 24 | CLI does not implicitly refresh | PASS | Writes are explicit seed/normalize/calculate; reads use query Tools. |
| 25 | Fixture remains NOT_LIVE | PASS | CLI/API output shows FIXTURE/OFFLINE/NOT_LIVE. |
| 26 | Live sources remain BLOCKED | PASS | Separate run: three explained skips, HTTP NOT_ATTEMPTED. |
| 27 | No RAG | PASS | Boundary/source tests pass. |
| 28 | No model call | PASS | No model SDK or invocation added. |
| 29 | No Agent | PASS | No Agent runtime/workflow added. |
| 30 | No MCP Server | PASS | Only reusable schemas; no MCP server/protocol implementation. |
| 31 | No target price | PASS | Source/docs scan; metrics are non-narrative. |
| 32 | No trading function | PASS | No broker/order/transaction path added. |
| 33 | Migration upgrades and rolls back | PASS | Dev and isolated 0004→0003→0004 end at 0004 head. |
| 34 | PostgreSQL integration passes | PASS | Nine focused migration/repository tests plus full integration suite. |
| 35 | Industrial FII is reproducible | PASS | Same snapshot, empty checksum and calculation run reused; honest BLOCKED. |
| 36 | Micron is reproducible | PASS | Same snapshot, empty checksum and calculation run reused; honest BLOCKED. |
| 37 | Documented commands execute | PASS | CLI help and corrected sample commands verified. |
| 38 | All prior tests pass | PASS | Final default suite: 1115 passed. |
| 39 | No unexplained default skips | PASS | Default run: zero skipped; Live's three skips are separate and explained. |
| 40 | No mass low-value tests | PASS | 145 Stage 5 tests cover distinct contracts/golden cases; parameters enumerate actual concepts/units/formulas, not empty duplication. |

## Final evidence

```text
uv sync                              resolved 54; checked 53; exit 0
uv run ruff check .                  All checks passed; exit 0
uv run ruff format --check .         166 files already formatted; exit 0
uv run mypy src                      no issues in 94 source files; exit 0
uv run pytest -W error               1115 passed in 199.83s; 0 warnings/skips
explicit live_tests                  3 explained BLOCKED skips; HTTP NOT_ATTEMPTED
```

The architecture and offline contracts pass, but authorized Live numeric evidence is
still unavailable. The appropriate stage decision is `CONDITIONAL GO`, never a fake
Live or complete-sample claim. Stage 6 has not started.
