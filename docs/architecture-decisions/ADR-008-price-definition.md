# ADR-008: V0.1 Price Definition

- Status: Accepted for V0.1
- Date: 2026-07-11

## Decision

V0.1 “current price” means:

> The latest available regular-session daily closing price eligible at `research_as_of_time`; no realtime quote is promised.

The price record must include security, exchange, market date, exchange timezone, close, currency, raw/adjusted flag, corporate-action basis, provider, provider timestamp if available, retrieval time and snapshot ID. If the research cutoff precedes that market's close, use the prior completed trading day's close. After-hours prices and stale web-page values are not closing prices.

Valuation uses raw close with current shares and explicitly handled corporate actions. Adjusted close is for return series, not market capitalization.

## Consequences

Realtime entitlements and streaming are unnecessary. “Latest” is reproducible and may differ between markets/timezones.
