# Public Fixture Replacement Matrix

## Purpose

The Public Export excludes all source-derived SEC, SSE, and Nasdaq Fixture payloads.
Their replacements are project-authored, minimal, offline test assets. They preserve the
schemas and boundary behavior exercised by the tests without reproducing a real filing,
company announcement, market-data series, or complete financial dataset.

Every replacement is marked `SYNTHETIC_TEST_ONLY`, `NOT_COMPANY_EVIDENCE`,
`NOT_PROVIDER_DATA`, `OFFLINE`, and `NOT_LIVE`. The fixed manifests also declare
`synthetic=true`, `test_only=true`, `company_evidence=false`, and `live=false`.

## Replacement map

| test_name | original_fixture | original_source_type | redistribution_status | synthetic_replacement | behaviors_preserved | assertions_preserved | limitation |
|---|---|---|---|---|---|---|---|
| `test_governed_sec_fixture_files_exist` | SEC submissions crop | Official-response metadata crop | Excluded pending review | `tests/fixtures/providers/sec_synthetic/tstx_sec_public.*` | Governed payload/manifest pair | Both files exist | No real issuer evidence |
| `test_sec_fixture_checksum_and_lf_bytes_are_independently_reproducible` | SEC submissions crop | Official-response metadata crop | Excluded pending review | `tstx_sec_public.json` | Fixed bytes, SHA-256, LF | Independent golden hash and byte count | Synthetic metadata only |
| `test_sec_fixture_manifest_is_project_authored_offline_and_not_live` | SEC manifest | Source-derived manifest | Excluded with payload | `tstx_sec_public.manifest.json` | Provenance and publication boundary | Required flags and markers | Cannot validate SEC redistribution |
| `test_sec_fixture_contains_only_synthetic_metadata_not_company_body` | SEC submissions crop | Real issuer metadata | Excluded pending review | `tstx_sec_public.json` | Submissions JSON, CIK, accession, form, dates, primary document | Exact synthetic issuer and three filing rows | No filing body or real company facts |
| `test_fixture_payload_bytes_are_pinned_to_lf_across_git_checkouts` | SSE, Nasdaq, SEC crops | Source-derived provider responses | Excluded pending review | Three package `*_public.json` payloads | LF-stable bytes | No CRLF and terminal LF | One minimal row per market payload |
| `test_manifest_has_strict_provenance_and_exact_payload_checksum[test001_sse_public-expected0]` | SSE market-data crop | Real market-data crop | Excluded pending review | `test001_sse_public.*` | SSE-shaped row, currency, source metadata, checksum | Exact manifest fields and synthetic markers | Not exchange or company evidence |
| `test_manifest_has_strict_provenance_and_exact_payload_checksum[tstx_nasdaq_public-expected1]` | Nasdaq market-data crop | Real market-data crop | Excluded pending review | `tstx_nasdaq_public.*` | Nasdaq-shaped row, OHLCV, currency, checksum | Exact manifest fields and synthetic markers | Not licensed market data |
| `test_manifest_has_strict_provenance_and_exact_payload_checksum[tstx_sec_public-expected2]` | SEC submissions crop | Official-response metadata crop | Excluded pending review | Package `tstx_sec_public.*` | SEC-shaped metadata and checksum | Exact manifest fields and synthetic markers | No filing body |
| `test_manifest_rejects_unknown_fields_and_false_capture_precision` | Three source manifests | Source-derived manifests | Excluded with payloads | Three strict synthetic manifests | Closed schema and honest timestamp precision | Unknown fields and false precision rejected | No source-capture claim |
| `test_payloads_equal_the_explicit_stage1_evidence_allowlist` | Old runtime resource names | Source-derived resource allowlist | Excluded pending review | `test001_sse_public`, `tstx_nasdaq_public`, `tstx_sec_public` | Explicit resource governance | Exact three-name allowlist | Public allowlist differs from historical tree |
| `test_loader_returns_verified_exact_package_bytes[test001_sse_public]` | SSE package crop | Real market-data crop | Excluded pending review | `test001_sse_public.json` | Loader verification before use | Returned bytes equal independently fixed asset | Synthetic one-row envelope |
| `test_loader_returns_verified_exact_package_bytes[tstx_nasdaq_public]` | Nasdaq package crop | Real market-data crop | Excluded pending review | `tstx_nasdaq_public.json` | Loader verification before use | Returned bytes equal independently fixed asset | Synthetic one-row envelope |
| `test_loader_returns_verified_exact_package_bytes[tstx_sec_public]` | SEC package crop | Official-response metadata crop | Excluded pending review | `tstx_sec_public.json` | Loader verification before parsing | Returned bytes equal independent golden copy | Synthetic metadata only |

The remaining generic loader tests continue to verify checksum-before-JSON behavior and
import-time non-I/O. The Tushare empty protocol Fixture was already project-authored and
therefore required no replacement.

## Synthetic identities and fixed checksums

- CN: `TEST001.SH`, Example Test Share Co., Ltd.; SHA-256
  `50059c707187f0c790332b47efdff99a8bb8b5af981323d5932fe82ba19b0eae`.
- US market: `TSTX`, Example Test Technologies Inc.; SHA-256
  `039ab7cfb7bdfd4929962588f0464c1d517baa3a3b898a4c28b574cb48e28936`.
- SEC metadata: Example Semiconductor Research Corp., test-only CIK
  `0000000000`; SHA-256
  `502f30807726be7ed4f09acb6f8e598cd4c5336d805e6c81c82be86209d24350`.

These hashes are fixed expected values. Tests do not ask the implementation under test
to generate its own golden expected output.
