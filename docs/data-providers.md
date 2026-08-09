# Stage 4 data providers

Stage 4 uses an offline-fixture-first ports-and-adapters design. A Provider is a
source contract, not a claim that a live feed is available. `DataProvider` stores
stable code, type, status, terms state and declared capabilities; it never stores a
token. `ProviderInstrumentMapping` binds a Stage 3 `security_id` to the provider's
symbol or instrument identifier with an effective interval. Provider selection is
exact and deterministic; API callers and read-only Tools cannot choose arbitrary
URLs or create mappings.

## Approved offline evidence

`STAGE1_SSE_FIXTURE`, `STAGE1_NASDAQ_FIXTURE`, and `STAGE1_SEC_FIXTURE` load only
checksum-verified safe crops documented in [fixture-sources.md](fixture-sources.md).
Every returned envelope is visibly `FIXTURE`, `OFFLINE`, and `NOT_LIVE`. The files
are reproducible development evidence, not current quotes or proof of production
rights. Each manifest records provider, endpoint/source URL, security,
`captured_at`, `source_published_at` when known, content type, crop rule, SHA-256,
and use restrictions.

## Capability and Live status

Capabilities such as `DAILY_PRICES`, `FINANCIAL_FACTS`, and `FILING_METADATA` state
what an adapter contract can represent. They do not imply availability. Live
`TUSHARE_PRO` remains `BLOCKED` without a real token and confirmed cache/use terms;
a licensed U.S. EOD source remains `BLOCKED` without a named provider, credential,
and license; `SEC_ARCHIVES` remains `BLOCKED` without a real SEC contact/User-Agent
and an implemented authorized adapter. No fake email, key, entitlement, response,
or Live PASS is accepted.

The separate `live_tests/` harness requires `RUN_LIVE_PROVIDER_TESTS=1` plus
provider configuration and is excluded from default pytest and CI. At present all
three Live sources record `BLOCKED` and `http_result=NOT_ATTEMPTED`.

## Current boundary

Providers depend on typed requests and return typed envelopes. They do not create a
database Session. Repositories do not call providers. Only an explicit CLI/internal
ingestion service may perform `INTERNAL_WRITE`; API and registered Tools remain
`READ_ONLY`. Stage 4 does not add 财务标准化, TTM, 财务指标, 估值, RAG, Agent, MCP, or
自动交易, and 不得进入第5阶段.
# Stage 9 production Provider governance

The fixed execution gate order is: Definition → Capability → License → Policy → Configuration
→ Credential Reference → Live Authorization → Rate Limit → Circuit Breaker → Budget → HTTP.
Failure at any gate is fail-closed and later gates do not run.

`SEC_EDGAR_PUBLIC_V1` has offline contract coverage and production state
`CONDITIONAL`; Live remains `NOT_ATTEMPTED` until contact identity and a separate
finite authorization are supplied. `TUSHARE_PRO_V1` has offline parser/planner
contracts but production state `BLOCKED` because license/entitlement and an
approved HTTPS endpoint are unresolved. Credential reference metadata may be
queried, but credential values are never returned or logged.
The lower-case contract term credential reference means the same immutable metadata.

Other U.S. EOD, A-share disclosure-body, and production Embedding providers stay
`BLOCKED`. This engineering status is `CONDITIONAL GO`, not evidence of Live data
availability and not authorization for Stage 10.
