# Metric Definitions V0.1

These definitions apply only to ordinary non-financial operating companies. Banks, insurers, brokers, funds, REITs and issuers whose statements cannot be normalized to these inputs are not applicable.

## Mandatory conventions for every metric

- **Arithmetic:** financial amounts, shares, prices, ratios and intermediate values use Python `Decimal`, never binary floating point. Source strings are parsed directly into `Decimal`; rounding occurs only at presentation.
- **Sign normalization:** stored canonical expenses/costs are positive magnitudes unless a metric explicitly uses a signed cash-flow value. Provider signs are normalized with lineage; formulas do not silently apply `abs()`.
- **Currency:** addition/subtraction and valuation require a single currency and compatible measurement basis. Cross-currency inputs require an explicit FX source, rate timestamp and conversion record; V0.1 otherwise returns missing.
- **Units:** every amount is normalized to base currency units before calculation while preserving source unit and scale. Shares are actual shares; per-share metrics are currency/share.
- **Missing values:** missing is `null` plus a machine-readable reason such as `SOURCE_MISSING`, `INCOMPATIBLE_PERIOD`, `INCOMPATIBLE_CURRENCY`, `DENOMINATOR_ZERO`, `NOT_MEANINGFUL` or `NOT_APPLICABLE`. Missing is never zero.
- **Corrections:** later amended/corrected filings may supersede facts only when `filed_at <= research_as_of_time`. The calculation records every selected accession/document and retains the superseded fact in lineage.
- **Annual/quarter/TTM:** annual means an issuer fiscal year. Quarter means a discrete issuer fiscal quarter. TTM is the sum of the latest four compatible discrete fiscal quarters available by the research cutoff.
- **Average balances:** where required, `(opening_balance + closing_balance) / 2`. If the opening balance is missing, the ratio is missing rather than silently using the closing balance.
- **Shares:** point-in-time valuation uses actual common shares outstanding at the price date. EPS uses the issuer-reported weighted-average basic or diluted shares for that exact period. These share types are never interchanged.
- **Parent versus total:** `net_income_parent` pairs with equity attributable to parent/common shareholders. Total consolidated net income pairs with total assets/total invested capital. Minority interest is not silently dropped.
- **Negative and zero denominators:** rules below override ordinary division. A ratio that is not economically meaningful is represented as `NM`, not `0` or an infinite number.
- **Formula version:** all outputs include a semantic `formula_version`; any change to definition or input selection increments it.

## Quarter construction

### A-share cumulative reports

For income-statement and cash-flow duration facts with compatible accounting scope and units:

- `Q1 = Q1_YTD`
- `Q2 = H1_YTD - Q1_YTD`
- `Q3 = Q3_YTD - H1_YTD`
- `Q4 = FY - Q3_YTD`

Balance-sheet facts are point-in-time and are never differenced. A reported `本报告期` current-quarter value may be used only after confirming its definition and statement scope; official cumulative statements remain the reconciliation control. If periods come from different filing versions, the system first selects the latest mutually compatible values available at the research cutoff.

### U.S. fiscal years

Calendar labels do not define quarters. Use filing `start`, `end`, `fy`, `fp`, form, accession and duration. Micron's week-based fiscal periods are grouped by the issuer's fiscal calendar. When a 10-K supplies only annual duration values, `Q4 = FY - Q1 - Q2 - Q3` using compatible discrete quarters; 10-Q year-to-date facts are used as reconciliation evidence, not double-counted.

## Metric catalogue

Each entry explicitly supplies all required fields. “Common rules” refers to the mandatory conventions above.

### 1. Revenue Growth

- **Metric name / key / Chinese:** Revenue Growth / `revenue_growth` / 营业收入增长率
- **Formula:** `(revenue_current - revenue_comparable_prior) / revenue_comparable_prior`
- **Inputs / source:** canonical revenue from normalized income statements; official filing is reconciliation source.
- **Period:** annual YoY, discrete-quarter YoY, or TTM YoY; label the variant. No sequential-quarter default.
- **Average balance:** no. **Currency/unit:** both revenues same currency, units and accounting scope.
- **Negative/zero:** negative current revenue is flagged anomalous; prior revenue `<= 0` returns `NM`.
- **Missing/corrections/shares:** common rules; shares not applicable.
- **Applicable/not applicable:** non-financial operating issuers; not applicable when predecessor/comparable scope is materially different without pro-forma reconciliation.
- **Test requirement:** positive, negative, prior-zero, unit mismatch, and restated-prior cases.

### 2. Gross Margin

- **Metric name / key / Chinese:** Gross Margin / `gross_margin` / 毛利率
- **Formula:** `(revenue - cost_of_revenue) / revenue`, equivalent to `gross_profit / revenue` only when reconciliation holds.
- **Inputs/source:** normalized revenue and cost of revenue from the same income statement.
- **Period:** annual, discrete quarter or TTM. **Average:** no. **Currency/unit:** same currency/unit.
- **Negative/zero:** negative margin is valid with warning; revenue `<= 0` is `NM`.
- **Missing/corrections/shares:** missing cost means missing margin; never infer cost from a percentage. Common correction rules; shares N/A.
- **Applicable/not applicable:** ordinary issuers reporting comparable cost of revenue; not applicable if gross profit/cost is not disclosed or classifications are incompatible.
- **Tests:** normal, negative gross profit, zero revenue, sign normalization, missing cost.

### 3. Operating Margin

- **Metric name / key / Chinese:** Operating Margin / `operating_margin` / 营业利润率
- **Formula:** `operating_income / revenue`.
- **Inputs/source:** GAAP/PRC-GAAP operating income and revenue for same scope; do not substitute EBIT or adjusted operating income.
- **Period:** annual, discrete quarter, TTM. **Average:** no. **Currency/unit:** same.
- **Negative/zero:** negative result is valid; revenue `<=0` is `NM`.
- **Missing/corrections/shares/applicability:** common rules; N/A if operating income cannot be mapped consistently.
- **Tests:** positive/negative operating income, zero revenue, adjusted-versus-GAAP rejection.

### 4. Net Margin

- **Metric name / key / Chinese:** Net Margin / `net_margin_parent` / 归母净利率
- **Formula:** `net_income_parent / revenue`.
- **Inputs/source:** profit attributable to parent/common shareholders and consolidated revenue; never total net income.
- **Period:** annual, discrete quarter, TTM. **Average:** no. **Currency/unit:** same.
- **Negative/zero:** negative margin valid; revenue `<=0` is `NM`.
- **Missing/corrections/shares/applicability:** common rules; not applicable if parent attribution is unavailable.
- **Tests:** parent/NCI separation, loss, zero revenue, correction.

### 5. ROE

- **Metric name / key / Chinese:** Return on Equity / `roe_parent` / 归母净资产收益率
- **Formula:** `net_income_parent / average_equity_parent`.
- **Inputs/source:** parent net income and beginning/ending equity attributable to parent/common shareholders.
- **Period:** annual or TTM; quarter may be unannualized and must carry `annualized=false`. **Average:** yes.
- **Currency/unit:** same currency and scope.
- **Negative/zero:** loss yields negative ROE only when average equity is positive; average equity `<=0` returns `NM`.
- **Missing/corrections/shares:** opening equity required; common correction rules; shares N/A.
- **Applicability:** non-financial issuers; not meaningful with non-positive equity or major unmatched recapitalization.
- **Tests:** normal, loss, negative equity, missing opening, large equity transaction warning.

### 6. ROA

- **Metric name / key / Chinese:** Return on Assets / `roa_total` / 总资产收益率
- **Formula:** `net_income_total / average_total_assets`.
- **Inputs/source:** total consolidated net income including NCI, and beginning/ending total assets.
- **Period:** annual or TTM; quarter unannualized unless explicitly configured. **Average:** yes.
- **Currency/unit:** same. **Negative/zero:** loss valid; average assets `<=0` is `NM`.
- **Missing/corrections/shares/applicability:** common; not use parent income in numerator; shares N/A; non-financial only.
- **Tests:** NCI case, loss, missing opening assets, zero assets.

### 7. ROIC

- **Metric name / key / Chinese:** Return on Invested Capital / `roic` / 投入资本回报率
- **Formula:** `NOPAT / average_invested_capital`; `NOPAT = operating_income * (1 - effective_tax_rate)`; `invested_capital = total_equity + interest_bearing_debt - cash_and_cash_equivalents`.
- **Inputs/source:** reported operating income, pretax income, income-tax expense, total equity, enumerated interest-bearing debt, cash/equivalents.
- **Period:** annual or TTM. **Average:** yes, opening and closing invested capital.
- **Currency/unit:** single currency/unit.
- **Negative/zero:** negative NOPAT can produce negative ROIC if average capital positive. Capital `<=0` is `NM`. Effective tax rate is usable only when pretax income `>0` and rate lies in `[0,1]`; otherwise ROIC is missing—no statutory-rate substitution in V0.1.
- **Missing/corrections/shares:** any missing debt/cash/equity/tax component yields missing; common correction rules; shares N/A.
- **Applicability:** ordinary non-financial issuers; not applicable to financials or where operating income/tax cannot be isolated.
- **Tests:** normal, loss/tax anomaly, negative capital, missing debt component, parent-vs-total scope.

### 8. Operating Cash Flow

- **Metric name / key / Chinese:** Operating Cash Flow / `operating_cash_flow` / 经营活动现金流量净额
- **Formula:** issuer-reported net cash provided by/used in operating activities; no reconstruction.
- **Inputs/source:** cash-flow statement canonical fact.
- **Period:** annual, discrete quarter or TTM. **Average:** no. **Currency/unit:** base currency amount.
- **Negative/zero:** signed value is valid, including zero.
- **Missing/corrections/shares/applicability:** common; cumulative A-share values must be differenced; shares N/A; non-financial and financial statements can report it, but V0.1 excludes financials.
- **Tests:** positive/negative, A-share Q3 differencing, missing fact, amended filing.

### 9. Free Cash Flow

- **Metric name / key / Chinese:** Free Cash Flow / `free_cash_flow` / 自由现金流
- **Formula:** `operating_cash_flow - capital_expenditure`.
- **Inputs/source:** reported OCF and cash paid for purchases/additions of PP&E plus explicitly identified capitalized intangible/software additions. Acquisitions, investments and leases are not silently included.
- **Period:** annual, discrete quarter, TTM. **Average:** no. **Currency/unit:** same.
- **Negative/zero:** signed result valid. **Missing:** if capex cannot be identified consistently, FCF is missing; never approximate from asset-balance changes.
- **Corrections/shares/applicability:** common; shares N/A; not comparable when capex classification changes without reconciliation.
- **Tests:** positive/negative FCF, missing capex, acquisition exclusion, cumulative-quarter differencing.

### 10. Debt Ratio

- **Metric name / key / Chinese:** Debt Ratio / `liabilities_to_assets` / 资产负债率
- **Formula:** `total_liabilities / total_assets`.
- **Inputs/source:** same-date consolidated balance-sheet totals.
- **Period:** point-in-time. **Average:** no. **Currency/unit:** same.
- **Negative/zero:** assets `<=0` is `NM`; negative liability is anomalous and rejected.
- **Missing/corrections/shares/applicability:** common; shares N/A; non-financial only for V0.1.
- **Tests:** normal, zero assets, unit mismatch, date mismatch.

### 11. Net Debt

- **Metric name / key / Chinese:** Net Debt / `net_debt` / 净债务
- **Formula:** `interest_bearing_debt - cash_and_cash_equivalents`.
- **Inputs/source:** enumerated short/long-term borrowings, current portion, bonds/notes and other confirmed interest-bearing debt; cash and cash equivalents only. Marketable securities are not netted in V0.1.
- **Period:** point-in-time. **Average:** no. **Currency/unit:** same.
- **Negative/zero:** negative value means net cash and is valid.
- **Missing:** an unclassified debt component makes the value missing, not zero. **Corrections/shares:** common; shares N/A.
- **Applicability:** non-financial issuers; not applicable where deposits/financing are operating liabilities.
- **Tests:** net cash, missing debt classification, currency mismatch, current-portion inclusion.

### 12. Basic EPS

- **Metric name / key / Chinese:** Basic EPS / `basic_eps` / 基本每股收益
- **Formula:** issuer-reported basic EPS for the exact period; validation formula is `income_available_to_common_basic / weighted_average_basic_shares` only when both inputs map exactly.
- **Inputs/source:** filing EPS fact and weighted-average basic shares.
- **Period:** annual, discrete quarter, TTM only by summing compatible discrete EPS when share/corporate-action policy confirms comparability; otherwise compute from TTM numerator and compatible weighted shares.
- **Average:** weighted shares by issuer, not balance average. **Currency/unit:** currency/share.
- **Negative/zero:** losses yield negative EPS. **Missing:** do not substitute diluted EPS.
- **Corrections/share changes:** use restated-for-split issuer figures where provided; record corporate action and filing version.
- **Applicability:** common equity; not applicable if basic share basis unavailable.
- **Tests:** profit/loss, basic-vs-diluted separation, split restatement, missing shares.

### 13. Diluted EPS

- **Metric name / key / Chinese:** Diluted EPS / `diluted_eps` / 稀释每股收益
- **Formula:** issuer-reported diluted EPS; validation uses income available to common divided by weighted-average diluted shares with anti-dilutive instruments excluded according to accounting rules.
- **Inputs/source:** filing diluted EPS and diluted weighted shares.
- **Period/average/currency:** same policies as Basic EPS.
- **Negative/zero:** negative valid; diluted EPS may equal basic in loss periods. **Missing:** never substitute basic EPS.
- **Corrections/share changes/applicability/tests:** common plus anti-dilution, options/convertibles and split-restatement cases.

### 14. PE

- **Metric name / key / Chinese:** Price/Earnings / `pe_ttm_diluted` / 市盈率（TTM，稀释）
- **Formula:** `market_cap_at_price_time / net_income_parent_ttm`; reconciliation alternative `price / diluted_eps_ttm` only when share bases align.
- **Inputs/source:** latest available daily close, actual shares outstanding at that market date, TTM parent net income; diluted EPS is a cross-check, not mixed with basic EPS.
- **Period:** point-in-time valuation over TTM earnings. **Average:** no. **Currency/unit:** price, market cap and earnings same currency.
- **Negative/zero:** TTM earnings `<=0` returns `NM`, never a negative PE.
- **Missing/corrections/share changes:** common; price/date and share-date must align; corporate actions after financial period are reflected in current shares.
- **Applicability:** positive-earnings ordinary issuers; not Forward PE and no consensus inputs.
- **Tests:** positive, loss, zero income, price/share-date mismatch, currency mismatch.

### 15. PB

- **Metric name / key / Chinese:** Price/Book / `pb_parent` / 市净率
- **Formula:** `market_cap_at_price_time / equity_parent_latest`.
- **Inputs/source:** latest daily close, actual shares outstanding, latest parent/common equity available by research cutoff.
- **Period:** point-in-time. **Average:** no. **Currency/unit:** same.
- **Negative/zero:** parent equity `<=0` returns `NM`; do not output negative PB.
- **Missing/corrections/share changes/applicability:** common; valuation date warning if equity is stale; not applicable with non-positive book value.
- **Tests:** positive, negative/zero equity, stale balance date, share change.

### 16. PS

- **Metric name / key / Chinese:** Price/Sales / `ps_ttm` / 市销率（TTM）
- **Formula:** `market_cap_at_price_time / revenue_ttm`.
- **Inputs/source:** price, actual shares, TTM revenue.
- **Period:** point-in-time over TTM. **Average:** no. **Currency/unit:** same.
- **Negative/zero:** revenue `<=0` is `NM`. **Missing/corrections/share changes:** common.
- **Applicability:** ordinary issuers with meaningful revenue; not comparable across pass-through revenue models without warning.
- **Tests:** normal, zero revenue, currency mismatch, share change.

### 17. Enterprise Value

- **Metric name / key / Chinese:** Enterprise Value / `enterprise_value` / 企业价值
- **Formula:** `market_cap + interest_bearing_debt + preferred_equity + noncontrolling_interest - cash_and_cash_equivalents`.
- **Inputs/source:** price-date market cap and latest compatible balance-sheet components.
- **Period:** point-in-time. **Average:** no. **Currency/unit:** same.
- **Negative/zero:** negative EV is valid but warned. **Missing:** preferred equity or NCI may be zero only when explicitly confirmed zero; missing is not zero.
- **Corrections/share changes:** common; align price/share date and disclose balance-sheet date lag.
- **Applicability:** non-financial operating issuers.
- **Tests:** normal, net-cash negative EV, missing NCI, preferred equity, currency mismatch.

### 18. EV/EBITDA

- **Metric name / key / Chinese:** EV/EBITDA / `ev_to_ebitda_ttm` / 企业价值倍数
- **Formula:** `enterprise_value / ebitda_ttm`.
- **Inputs/source:** defined EV and EBITDA TTM under metric 22.
- **Period:** point-in-time EV over TTM. **Average:** no. **Currency/unit:** same.
- **Negative/zero:** EBITDA `<=0` returns `NM`; negative EV with positive EBITDA may be numeric with warning.
- **Missing:** missing EBITDA returns missing; no model estimate or substituted adjusted EBITDA.
- **Corrections/shares/applicability:** inherit EV and EBITDA rules; not applicable where EBITDA is unavailable/inappropriate.
- **Tests:** normal, negative/zero/missing EBITDA, negative EV, definition mismatch.

### 19. Free Cash Flow Yield

- **Metric name / key / Chinese:** Free Cash Flow Yield / `fcf_yield_ttm` / 自由现金流收益率（TTM）
- **Formula:** `free_cash_flow_ttm / market_cap_at_price_time`.
- **Inputs/source:** FCF TTM and market cap.
- **Period:** point-in-time over TTM. **Average:** no. **Currency/unit:** same.
- **Negative/zero:** negative yield is valid; market cap `<=0` is `NM`.
- **Missing/corrections/share changes/applicability:** inherit FCF and market-cap policies.
- **Tests:** positive/negative FCF, zero market cap, missing capex, currency mismatch.

### 20. Revenue TTM

- **Metric name / key / Chinese:** Revenue TTM / `revenue_ttm` / 过去十二个月营业收入
- **Formula:** `sum(latest_four_discrete_quarter_revenue)`.
- **Inputs/source:** four normalized compatible discrete fiscal quarters.
- **Period:** rolling four fiscal quarters. **Average:** no. **Currency/unit:** one currency/base unit.
- **Negative/zero:** zero allowed but warned; negative revenue anomalous. **Missing:** any missing/incompatible quarter makes TTM missing.
- **Corrections/shares/applicability:** latest versions available by cutoff; shares N/A; non-financial issuers.
- **Tests:** A-share Q4 derivation, Micron week-based quarters, missing quarter, restated quarter, unit mismatch.

### 21. Net Income TTM

- **Metric name / key / Chinese:** Net Income TTM / `net_income_parent_ttm` / 过去十二个月归母净利润
- **Formula:** `sum(latest_four_discrete_quarter_net_income_parent)`.
- **Inputs/source:** parent-attributable discrete-quarter earnings only.
- **Period/average/currency:** rolling four quarters; no average; same currency/unit.
- **Negative/zero:** signed value valid. **Missing:** total net income cannot substitute for parent income.
- **Corrections/shares/applicability/tests:** common; A-share differencing, U.S. Q4 derivation, loss, missing parent attribution, restatement.

### 22. EBITDA TTM

- **Metric name / key / Chinese:** EBITDA TTM / `ebitda_ttm` / 过去十二个月息税折旧摊销前利润
- **Formula:** sum of four compatible discrete-quarter EBITDA values. A quarter's EBITDA may equal `operating_income + depreciation + amortization` only when depreciation and amortization totals for that exact period are explicitly reported and mapped without double counting.
- **Inputs/source:** official GAAP/PRC-GAAP operating income and explicit D&A, or issuer-reported GAAP-reconciled EBITDA whose definition is stored. Adjusted EBITDA is a distinct, non-canonical metric.
- **Period:** rolling four fiscal quarters. **Average:** no. **Currency/unit:** same.
- **Negative/zero:** signed EBITDA valid. **Missing:** if total D&A or a compatible issuer EBITDA is absent, return missing; do not estimate from capex, accumulated depreciation or model inference.
- **Corrections/shares/applicability:** common; shares N/A; not applicable where EBITDA obscures economically essential costs.
- **Tests:** explicit D&A, missing D&A, double-count prevention, adjusted EBITDA rejection, four-quarter compatibility.

## V0.1 scenario valuation strategy

V0.1 may first implement one minimal, testable multiple-based scenario template, but no method is a universal permanent default. Selection considers positive/negative earnings, earnings stability, cyclicality, capital intensity, available fields and whether balance-sheet/share inputs can be reconciled. The selected method, rejected methods and fallback reason are report data, not hidden code choices.

Supported deterministic templates may include:

```text
# PE / normalized earnings
scenario_equity_value = scenario_net_income_parent × scenario_exit_pe
scenario_per_share_value = scenario_equity_value / actual_common_shares_outstanding

# EV / EBITDA
scenario_ev = scenario_ebitda × scenario_exit_ev_to_ebitda
scenario_equity_value = scenario_ev - debt - preferred_equity - NCI + cash
scenario_per_share_value = scenario_equity_value / actual_common_shares_outstanding

# EV / Revenue
scenario_ev = scenario_revenue × scenario_exit_ev_to_revenue
scenario_equity_value = scenario_ev - debt - preferred_equity - NCI + cash
scenario_per_share_value = scenario_equity_value / actual_common_shares_outstanding

# PB
scenario_equity_value = scenario_book_equity_parent × scenario_exit_pb
scenario_per_share_value = scenario_equity_value / actual_common_shares_outstanding
```

Method rules:

- **PE:** candidate when attributable earnings are positive and sufficiently representative; use normalized/mid-cycle earnings for cyclical cases and disclose normalization.
- **EV/EBITDA:** candidate when EBITDA is explicitly available/reconstructable under metric 22 and capital structure matters; unavailable EBITDA cannot be estimated.
- **EV/Revenue:** fallback or auxiliary method when profit/EBITDA is not meaningful but revenue is positive; it is not a universal answer.
- **PB:** auxiliary method when book capital is economically meaningful; non-positive parent equity is `NM`.

Sample-company recommendation for later implementation:

| Company | Recommended primary method | Auxiliary methods | Rationale/boundary |
|---|---|---|---|
| Industrial FII `601138.SH` | PE on attributable TTM/normalized earnings | EV/EBITDA when explicit compatible D&A exists; EV/Revenue as sensitivity | A profitable operating company can support an equity-earnings bridge. Margin/cycle normalization and share changes must be shown. PB is not the primary method. |
| Micron `MU` | Normalized/mid-cycle EV/EBITDA, only when EBITDA is deterministically available | PB and EV/Revenue; PE only as a supporting cross-check during representative positive earnings | Memory semiconductors are cyclical and capital intensive, so spot PE can be misleading at cycle extremes. EV/Revenue is an auxiliary/fallback, not the universal default. |

Every growth rate, normalized driver and valuation multiple is a `SCENARIO` assumption with author/source, rationale, horizon and sensitivity. It is never consensus or a confirmed fact. Preferred equity/NCI can be zero only when confirmed. A method with missing required fields is `UNAVAILABLE`; fallback requires an explicit reason and new calculation lineage. Any formula or selection-rule change increments the valuation formula version and is reviewed under ADR-009.

## Required test corpus for Stage 5

At minimum, implement table-driven Decimal tests for: ordinary profit, loss, zero denominator, negative equity, net cash, missing EBITDA, missing capex, unit/currency mismatch, parent-versus-total income, basic-versus-diluted EPS, A-share Q1/H1/Q3/FY differencing, Micron 52/53-week fiscal periods, amended filings before/after the research cutoff, share splits/dividends, and actual shares versus weighted-average shares.
