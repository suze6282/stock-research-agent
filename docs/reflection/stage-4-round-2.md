# Stage 4 Reflection — Round 2

## Conclusion

Round 2 rechecked all 30 required items against code, tests, PostgreSQL, CLI output,
OpenAPI contracts, migration replay, and the offline/Live separation. The core Stage 4
result is ready as **CONDITIONAL GO**. Unresolved counts are `CRITICAL=0` and
`HIGH=0`.

Two Round 2 issues were found and fixed through failing tests:

| Problem ID | Role | Severity | Description | Evidence | Affected files | Fix | Blocking | Status |
| --- | --- | --- | --- | --- | --- | --- | --- | --- |
| S4-R2-001 | Reliability/configuration | MEDIUM | The full gate found that `.env.example` omitted the new durable `BLOB_STORAGE_ROOT` Settings key. | Full PostgreSQL run failed `test_example_environment_matches_settings_contract`; the focused rerun then passed 53 tests. | `.env.example` | Added a safe absolute Windows placeholder; committed as `db31719`. | No | FIXED |
| S4-R2-002 | Tool/API contract | HIGH | A snapshot query for an absent category returned correct `PARTIAL` data but lost the snapshot's known fixture provenance and emitted `UNKNOWN`. | New four-case Tool test failed for prices/actions/facts/documents; the existing API facts contract also exposed the mismatch. | Tool support/adapters and Tool/API tests | Empty snapshot-category reads now derive bounded provider provenance from immutable snapshot items without fetching or writing. Focused Tool/API suite: 122 passed; committed as `5adfb2f`. | Yes | FIXED |

Round 1's `HIGH` durable-blob finding remains fixed. Its open `MEDIUM` orphan-blob
cleanup improvement and `LOW` exhaustive-scan limitation remain non-blocking and are
carried into the implementation report.

## Thirty required checks

| # | Check | Result | Actual evidence |
| ---: | --- | --- | --- |
| 1 | Provider interface and implementations agree | PASS | Registry/capability/fixture contracts and strict schemas passed in the 970-test run. |
| 2 | Capability declarations are accurate | PASS | SSE/Nasdaq crops expose daily data only; SEC crop exposes filing metadata and an honestly empty facts result. |
| 3 | Licensing is not overstated | PASS | Manifests and catalog retain experimental/personal-research restrictions; no production entitlement is claimed. |
| 4 | Fixture and Live are distinct | PASS | Runtime/Tool/CLI/API use `FIXTURE`, `OFFLINE`, `NOT_LIVE`; Live has a separate test directory. |
| 5 | HTTP client is centralized | PASS | Production search found the sole `httpx.Client` construction in `providers/http_client.py`. |
| 6 | No domain-allowlist bypass | PASS | HTTPS, DNS/IP, port and redirect revalidation tests passed; callers cannot supply arbitrary URLs. |
| 7 | Tokens do not enter logs | PASS | Redaction, safe URL, response error and configuration-summary tests passed. |
| 8 | RawPayload cannot be overwritten | PASS | Immutable blob/repository constraints and byte-for-byte reopening regression passed. |
| 9 | Revisions preserve history | PASS | PostgreSQL provider-revision acceptance creates a new payload/record/snapshot version. |
| 10 | as-of filtering works | PASS | Known post-cutoff publication and future trading dates are excluded in unit/contract/PostgreSQL tests. |
| 11 | Snapshots contain no future data | PASS | Required two-sample future counterexample passed. |
| 12 | COMPLETE snapshots are immutable | PASS | Repository guards plus PostgreSQL triggers reject terminal snapshot/item update, insertion and deletion. |
| 13 | Financial facts are not standardized | PASS | Raw provider concept, label, unit, context and flags remain; forbidden normalized fields are absent. |
| 14 | No TTM or financial metrics | PASS | Module/API/schema boundary tests and source scan found no calculation implementation. |
| 15 | No document parsing | PASS | Only source-document metadata is stored/read; no body download, parser or OCR exists. |
| 16 | No RAG | PASS | Dependency/module boundary tests and source scan passed. |
| 17 | No model call | PASS | No model SDK/runtime dependency or call exists. |
| 18 | No Agent | PASS | No Agent workflow/runtime exists. |
| 19 | No MCP Server | PASS | Only future-compatible schemas exist; no MCP package/server is present. |
| 20 | Tool read-only boundary works | PASS | Exactly eight v1 tools; all metadata says `READ_ONLY`, `writes=false`, `requires_network=false`. |
| 21 | CLI and API share services | PASS | Both compose `DataAccessQueryService` and canonical Tool Registry; writes remain explicit CLI-only services. |
| 22 | Default tests do not access the internet | PASS | Autouse loopback-only socket/DNS guard; full 970-test run completed offline. |
| 23 | Live tests are absent from default CI | PASS | Default `testpaths=tests`; CI sets provider networking false; explicit `live_tests` run is separate. |
| 24 | Migration upgrades and rolls back | PASS | Development upgrade/downgrade/upgrade and isolated base→0001→0002→0003→down→up both ended at 0003 head. |
| 25 | Real PostgreSQL integration passes | PASS | Full suite used the project PostgreSQL 17 test database on loopback, not SQLite. |
| 26 | 601138.SH snapshot is reproducible | PASS | Final replay reused ID `e56f0ebe-d2dd-41ff-bc0c-336bc8f114d0` and checksum `4d96ad2f...42aecec`; PARTIAL, one item. |
| 27 | MU snapshot is reproducible | PASS | Final replay reused ID `41860194-bf16-44e0-87b7-446c68805839` and checksum `4028976d...a3e52c`; PARTIAL, four items. |
| 28 | All original tests still pass | PASS | `970 passed in 150.92s`; Stage 2/3 suites remain collected. |
| 29 | Documentation agrees with code | PASS | Ten Stage 4 documentation tests plus executable CLI examples and configuration contract passed. |
| 30 | No unexplained skipped tests | PASS | Default full run had 970 passed and zero skipped; separate Live run had exactly three explained `BLOCKED` skips. |

## Final gate evidence

```text
uv sync                              Resolved 54; Checked 53; exit 0
uv run ruff check .                  All checks passed; exit 0
uv run ruff format --check .         129 files already formatted; exit 0
uv run mypy src                      no issues in 73 source files; exit 0
uv run pytest -W error               970 passed in 150.92s; 0 warnings/skips; exit 0
explicit live_tests                  3 explained BLOCKED skips; no HTTP attempted
```

## Live blockers and decision

- `TUSHARE_PRO`: token and cache/terms confirmation absent.
- `LICENSED_US_EOD`: named licensed provider, API key and license confirmation absent.
- `SEC_ARCHIVES`: real contact email and compliant User-Agent absent.

No Live request, payload, or snapshot was fabricated. These blockers prevent `GO`
but do not invalidate the fully offline Provider, ingestion, snapshot, Tool, API,
CLI, migration, and PostgreSQL contracts. Stage 5 has not been started or authorized.
