# Product Scope V0.1

## Product position

V0.1 is a personal, evidence-backed research assistant for two ordinary non-financial listed equities. It is not a trading system, advisory service, price-prediction product, or public market-data redistribution service.

**Target user:** one technically capable individual performing fundamental research for personal use.
**Core scenario:** enter `601138.SH`, `工业富联`, `MU`, or `Micron Technology`; receive a reproducible Markdown and JSON report based on a dated snapshot, deterministic calculations, cited filings, explicit gaps, and bounded Reflection.

## Inputs

- Security code, company name, or approved alias.
- `research_as_of_time` supplied by the caller or fixed at task creation.
- Optional scenario assumptions whose source and author are recorded.
- No portfolio size, risk tolerance, brokerage credentials, or order parameters.

## Outputs

- Modular JSON outputs and a human-readable Markdown report.
- Latest available daily close with market date, timezone, retrieval time, currency and source.
- Three annual periods and four available discrete fiscal quarters when source evidence permits.
- Deterministic metrics and valuation paths with formula version.
- Bear/base/bull scenarios explicitly classified as `SCENARIO`.
- Citations, supporting and contrary evidence, gaps, warnings, proof/disproof conditions and disclaimer.

## Scope register

| Capability | Status | V0.1 decision |
|---|---|---|
| Industrial FII `601138.SH` | `IN_SCOPE` | End-to-end sample A-share. |
| Micron `MU` | `IN_SCOPE` | End-to-end sample U.S. share. |
| Security identity and issuer/security distinction | `IN_SCOPE` | Exactly the two samples initially. |
| Latest available daily close | `IN_SCOPE` | Not realtime; see ADR-008. |
| Daily OHLCV history | `IN_SCOPE` | Only the history needed for source checks and price context. |
| Three annual periods | `IN_SCOPE` | Periods available at `research_as_of_time`; corrected filings supersede earlier versions without deleting lineage. |
| Four available discrete fiscal quarters | `IN_SCOPE` | A-share cumulative periods must be differenced deterministically. |
| A-share periodic and important announcements | `IN_SCOPE` | Official exchange/CNINFO documents preferred. |
| SEC 10-K, 10-Q and 8-K | `IN_SCOPE` | SEC Archives and submissions metadata. |
| Company official earnings materials | `IN_SCOPE` | Issuer IR domain only. |
| Deterministic metrics | `IN_SCOPE` | Decimal arithmetic and versioned formulas. |
| Three-scenario valuation | `IN_SCOPE` | Minimal testable method selected by profitability, cyclicality and field availability; EV/Revenue is only one candidate. All growth/multiple inputs are explicit `SCENARIO` assumptions. |
| Markdown and JSON reports with citations | `IN_SCOPE` | Modular schemas, not one oversized model. |
| Fixed orchestration | `IN_SCOPE` | Program owns required steps and quality gates. |
| Single analytical Agent | `IN_SCOPE` | Limited read-only tools only. |
| Reflection, maximum two rounds | `IN_SCOPE` | Stop conditions are mandatory. |
| Real-time or intraday prices | `OUT_OF_SCOPE` | No minute bars, streams or realtime entitlement. |
| Automatic trading or broker connection | `OUT_OF_SCOPE` | No orders, positions or credentials. |
| Personalized position sizing | `OUT_OF_SCOPE` | No personal balance-sheet input. |
| News-sentiment trading | `OUT_OF_SCOPE` | Not a V0.1 research requirement. |
| Broker consensus, target prices, Forward PE | `OUT_OF_SCOPE` | No licensed estimates source. Scenario assumptions are not consensus estimates. |
| Full-market screening or backtesting | `OUT_OF_SCOPE` | Two explicit securities only. |
| Multi-Agent | `OUT_OF_SCOPE` | One fixed pipeline and one Agent. |
| Production MCP Server | `OUT_OF_SCOPE` | Internal tool boundaries only. |
| Frontend and multi-user access | `OUT_OF_SCOPE` | Deferred to Stage 10. |
| Banks, insurers, brokers | `OUT_OF_SCOPE` | Metric definitions are for ordinary non-financial issuers. |
| ETF, REIT, ADR, multiple listings | `OUT_OF_SCOPE` | Different identity and accounting models. |
| Cryptoassets and futures | `OUT_OF_SCOPE` | Different markets and risk model. |
| Public/paid report service | `OUT_OF_SCOPE` | Requires new data and securities-advice reviews. |
| Paid A-share provider selection | `NEEDS_VALIDATION` | Tushare can support personal use but no token was present; institutional/commercial paths differ. |
| Licensed U.S. EOD provider selection | `NEEDS_VALIDATION` | Public Nasdaq website is only a feasibility probe, not a production entitlement. |
| Production model provider and deployment region | `NEEDS_VALIDATION` | Mainland OpenAI support is not established. |
| Vector model/vendor | `DEFERRED` | Decide in Stage 6 after deployment and data-location review. |

## Success criteria

V0.1 succeeds only when both sample securities can complete the same required pipeline with:

1. unambiguous identity;
2. source-dated daily close;
3. three annual and four discrete-quarter datasets, or an explicit `PARTIAL` result for a documented source gap;
4. reproducible Decimal calculations with unit/currency checks;
5. filing retrieval with citations that resolve to the supporting passage;
6. no future data relative to `research_as_of_time`;
7. a deterministic scenario calculation with assumptions shown;
8. Reflection completion within two rounds;
9. persisted snapshot, source, formula, prompt and model versions;
10. passing automated tests for all deterministic logic.

For announcement completeness, V0.1 acquires all available issuer announcements whose publication time falls from the start of the earliest included annual period through `research_as_of_time`; it then labels periodic reports, earnings/preliminary results, dividends/share changes, financing, major contracts/investments, related-party transactions, litigation/regulatory actions and other company/exchange-designated material events. Classification prioritizes review but never deletes unclassified announcements from the snapshot inventory.

## Failure criteria

V0.1 fails if either sample is misidentified; a key number cannot be traced; a cumulative quarter is treated as a discrete quarter; a future filing enters a historical snapshot; a calculation is performed only by the model; a citation does not support its claim; a data provider's permission is assumed; a missing value is invented; or the system presents a scenario as confirmed fact.

## V0.2 expansion gates

Expansion beyond the two samples requires both pipelines to pass acceptance tests across at least two restated/historical snapshots, data-provider terms to cover the intended use and storage, formula conformance tests, citation precision tests, bounded Reflection tests, provider health monitoring, and no unresolved `CRITICAL` risk. Expansion remains limited to ordinary non-financial A-share and U.S. common stock issuers.
