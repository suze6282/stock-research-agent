# Compliance Boundaries V0.1

## Position

V0.1 is a **personal-use research assistance tool**. This document records product boundaries, not legal advice.

## Allowed intent

- Organize and analyze publicly available/company-authorized information for one user's own research.
- Show sources, formulas, uncertainty, contrary evidence and gaps.
- Produce scenarios as assumptions, not promises or individualized recommendations.

## Prohibited in V0.1

- Automatic trading, broker connection, order generation or execution.
- Guaranteed returns, “certain to rise,” or similar claims.
- Position sizing based on personal assets, income, debts, risk tolerance or holdings.
- Charging the public for individualized investment advice or operating a public advisory service.
- Presenting model forecasts/inferences as confirmed facts.
- Redistributing raw or derived market data, consensus estimates, filings or provider content beyond the license.
- Treating a disclaimer as the only compliance measure.

## Data authorization boundary

Public accessibility does not equal permission to automate, cache, display, redistribute or use commercially. Each provider record must separately approve the intended actions. Tushare's reviewed terms grant personal, non-commercial, non-transferable use; future public/commercial use requires a new agreement. SSE information services are license-managed. Alpha Vantage's reviewed terms distinguish personal from commercial use. Nasdaq/other vendor dataset rights are product-specific. CNINFO/SSE website endpoint automation and cache/display rights remain unverified.

V0.1 may store only the minimum personal research cache supported by confirmed terms. Before any public UI, multi-user access, paid feature, shared report feed or company use, obtain a fresh written data-license review.

## Securities-advice boundary

The report should describe evidence, calculations and scenarios, not issue a personalized buy/sell instruction. If the project is offered to others, marketed, monetized or used by an organization, obtain qualified review of applicable securities-investment-consulting, advertising, consumer-protection and recordkeeping rules in every target jurisdiction.

## Required report language

- State data cutoff and that data can be incomplete or corrected.
- Distinguish `FACT`, `CALCULATION`, `INFERENCE`, `SCENARIO` and `UNVERIFIED`.
- State that scenarios are conditional, not forecasts or guarantees.
- Disclose provider/document gaps and conflicts.
- State that the tool does not consider the reader's personal situation and does not execute trades.

## Re-review triggers

Public launch, paid access, multi-user accounts, portfolio personalization, alerts, broker integration, realtime data, consensus data, new jurisdiction, company/institutional use, remote MCP exposure, or change of provider/model/deployment region.

# Stage 9 Provider compliance boundary

SEC public API/filing use is conditionally approved only behind fair-access,
declared-contact, endpoint, budget and artifact-rights gates; Live remains
`NOT_ATTEMPTED`. Tushare is `BLOCKED`: reviewed personal/non-commercial terms do
not establish production raw/cache/derived/redistribution rights or Token
entitlements. Other production sources remain blocked until separately reviewed.

Provider credential values are never persisted, logged, returned by Tool/API/CLI, or read
merely because an environment variable exists. Only versioned credential reference
metadata crosses the control plane. Every license decision covers acquisition,
storage, cache, derived use, redistribution, retention and deletion. Live needs
the exact separate authorization phrase and finite disclosure. The Stage 9 result
is `CONDITIONAL GO`; it neither proves real-company completeness nor authorizes
Stage 10.
