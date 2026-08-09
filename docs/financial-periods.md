# Financial period semantics

`FinancialPeriod` stores fiscal year/quarter/period, explicit type, start/end,
publication and filing dates, actual duration days, accounting basis, source form,
and cumulative/single-quarter/annual/TTM flags. Supported types are `ANNUAL`,
`QUARTER`, `HALF_YEAR`, `NINE_MONTH_YTD`, `YEAR_TO_DATE`, `TTM`, and `INSTANT`.

Duration facts require start and end dates; instant facts have one date and are never
de-accumulated or treated as TTM. U.S. periods use source FY/FP and actual dates, so
non-calendar and 52/53-week years remain visible. A 10-K is annual evidence and is
never relabeled as Q4. Q4 may be derived only by a validated FY minus comparable 9M
operation.

Eligible A-share cumulative duration facts use deterministic version `1.0.0` rules:
Q1 stays Q1; Q2 = H1 - Q1; Q3 = 9M - H1; Q4 = FY - 9M. Both inputs must match security,
concept, fiscal year, currency, normalized unit and accounting basis and be visible at
the snapshot cutoff. Derived facts are separate from reported facts and retain ordered
input IDs. Missing predecessors or incompatible bases produce `BLOCKED` warnings.

TTM supports two deterministic domain algorithms: four comparable single quarters,
or FY + latest YTD - prior-year comparable YTD. Neither annualizes one quarter nor
uses an annual value as TTM. Instant/balance-sheet facts and unsupported EPS contexts
are blocked. Actual duration mismatch and 53-week comparability are surfaced rather
than hidden.
