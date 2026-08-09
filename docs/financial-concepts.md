# Canonical financial concepts

Stage 5 separates immutable Stage 4 `ProviderFinancialFact` evidence from canonical
facts. A canonical code is a stable analytical identity, not a copy of a provider
label. The V0.1 dictionary contains 35 concepts and records statement, fact nature,
unit family, supported period shape, cumulative/TTM eligibility, sign policy, version,
and lifecycle status.

| Group | V0.1 codes |
| --- | --- |
| Income | `REVENUE`, `COST_OF_REVENUE`, `GROSS_PROFIT`, `OPERATING_INCOME`, `EBITDA`, `PRETAX_INCOME`, `INCOME_TAX_EXPENSE`, `NET_INCOME`, `NET_INCOME_ATTRIBUTABLE_TO_PARENT`, `BASIC_EPS`, `DILUTED_EPS` |
| Balance sheet | `CASH_AND_CASH_EQUIVALENTS`, `SHORT_TERM_INVESTMENTS`, `ACCOUNTS_RECEIVABLE`, `INVENTORY`, `TOTAL_CURRENT_ASSETS`, `TOTAL_ASSETS`, `SHORT_TERM_DEBT`, `LONG_TERM_DEBT`, `TOTAL_DEBT`, `TOTAL_CURRENT_LIABILITIES`, `TOTAL_LIABILITIES`, `TOTAL_EQUITY`, `EQUITY_ATTRIBUTABLE_TO_PARENT`, `MINORITY_INTEREST`, `PREFERRED_EQUITY` |
| Cash flow | `OPERATING_CASH_FLOW`, `CAPITAL_EXPENDITURES`, `INVESTING_CASH_FLOW`, `FINANCING_CASH_FLOW`, `CASH_DIVIDENDS_PAID`, `SHARE_REPURCHASES` |
| Shares | `BASIC_WEIGHTED_AVERAGE_SHARES`, `DILUTED_WEIGHTED_AVERAGE_SHARES`, `PERIOD_END_SHARES_OUTSTANDING` |

Parent-attributable and total income, basic and diluted EPS, weighted-average and
period-end shares, and duration and instant facts remain distinct. Deprecated
concepts stay readable but cannot become new default mappings. The transactional
`financials seed-v0` command seeds the dictionary; Alembic does not insert business
or reference data.
