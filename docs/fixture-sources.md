# Public Offline Fixture Sources

The Public Export contains only project-authored Synthetic Fixtures. Source-derived SEC,
SSE, and Nasdaq payloads from the development repository are deliberately excluded while
redistribution review remains unresolved. No excluded file is needed by the public test
suite.

## Synthetic SSE structure

- Resource: `test001_sse_public`
- Security: `TEST001.SH` / Example Test Share Co., Ltd.
- Content: one invented OHLCV row using simple round values
- Currency: CNY
- Purpose: parser, Decimal, normalization, checksum, manifest, as-of, and quality tests

## Synthetic Nasdaq structure

- Resource: `tstx_nasdaq_public`
- Security: `TSTX` / Example Test Technologies Inc.
- Content: one invented OHLCV row using simple round values
- Currency: USD
- Purpose: parser, normalization, checksum, manifest, as-of, and provider-contract tests

## Synthetic SEC structure

- Resource: `tstx_sec_public`
- Issuer: Example Semiconductor Research Corp.
- CIK: test-only `0000000000`
- Content: three invented filing-metadata rows for 10-K, 10-Q, and 8-K
- Body sentence: project-authored parser/citation test notice only
- Purpose: Company Submissions JSON shape, accession handling, dates, primary-document
  metadata, checksum, manifest, as-of, and future-data tests

No real filing paragraph, company announcement, market series, or complete financial
dataset is present. Reserved `.invalid` URLs prevent the metadata from being mistaken for
a reachable Provider endpoint.

## Tushare synthetic protocol envelope

The retained Tushare Fixture is a project-authored empty response envelope. It tests the
protocol contract and contains no credential, endpoint access, company evidence, or
licensed provider response.

## Governance

Each public Fixture has a fixed sibling manifest, exact byte count, SHA-256 checksum, LF
line endings, and explicit publication-boundary flags. Runtime resources are allowlisted;
unknown resources and manifest fields fail closed. See the
[Public Fixture Replacement Matrix](PUBLIC_FIXTURE_REPLACEMENT_MATRIX.md) for the
test-by-test mapping.

All public Fixtures are `SYNTHETIC_TEST_ONLY`, `NOT_COMPANY_EVIDENCE`,
`NOT_PROVIDER_DATA`, `OFFLINE`, and `NOT_LIVE`. They must never be cited as research
evidence or described as Live Provider validation.
