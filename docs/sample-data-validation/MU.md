# Sample Data Validation: MU

Validation date: 2026-07-11 +08:00
This is a feasibility check, not an investment report.

## Stage 9 offline production-provider acceptance

The facts below remain historical Stage 1 feasibility evidence. Stage 9 did not
repeat those network probes and does not treat them as current Live validation.

- SEC offline adapter and metadata contract: `PASS`.
- Stage 1 SEC submissions crop: `FIXTURE`, `OFFLINE`, `NOT_LIVE`, and metadata
  only.
- Verified company filing body: `BLOCKED`.
- Verified financial completion: `BLOCKED`; the accepted metadata crop contains
  an empty `financial_facts` collection.
- Licensed U.S. EOD Provider: `BLOCKED`.
- Live validation: `NOT_ATTEMPTED`.
- Synthetic fixtures accepted as company evidence: `0`.

Offline contract success does not authorize SEC Live access and does not make the
company evidence complete. No synthetic body or financial value is used to fill
the missing Micron evidence.

## Confirmed facts

| Item | Confirmed value | Evidence |
|---|---|---|
| Issuer | Micron Technology, Inc. | SEC submissions and Company Facts. |
| Ticker / CIK | `MU` / `0000723125` | SEC submissions endpoint. |
| Exchange | Nasdaq | SEC submissions returned `exchanges: ["Nasdaq"]`. |
| Currency | USD | Company Facts selected concepts use `USD` and `USD/shares`. |
| Fiscal year | Not the natural/calendar year | SEC reports fiscal-year-end code `0903`; FY2025 10-K report date is 2025-08-28. Micron uses week-based fiscal periods, so exact filing period dates control. |

## Actual validation results

| Check | Result | Evidence/qualification |
|---|---|---|
| Identity and CIK mapping | `VERIFIED` | SEC submissions returned name, ticker, exchange and CIK in one official response. |
| Latest available daily date | `2026-07-10` | Nasdaq public website endpoint returned daily rows. |
| Daily OHLCV availability | `PARTIALLY_VERIFIED` | Latest returned row: open `$964.975`, high `$998.00`, low `$954.13`, close `$979.30`, volume `31,768,090`. This proves website reachability only; it is not a documented production API entitlement. |
| 10-K | `VERIFIED` | Latest in SEC submissions: filed `2025-10-03`, report date `2025-08-28`, accession `0000723125-25-000028`. |
| 10-Q | `VERIFIED` | Latest: filed `2026-06-25`, report date `2026-05-28`, accession `0000723125-26-000015`. |
| 8-K | `VERIFIED` | SEC submissions returned multiple 8-Ks, including `0000723125-26-000013` filed `2026-06-24`. |
| XBRL Company Facts | `VERIFIED` | Official endpoint returned revenue, parent net income, assets, parent equity, dividends/share, basic EPS and diluted EPS with units. |
| Custom XBRL tags | `PARTIALLY_VERIFIED` | Earlier isolated Archive reads observed `mu:` custom tags, but the final standardized probe could not reproduce the document reads because SEC Archive returned 403. Tag counts are historical feasibility evidence, not a currently passing production check. |
| Company IR materials | `VERIFIED` | Micron IR returned FY2026 Q3 release, prepared remarks/deck links and SEC filing mirror. |
| Dividends | `PARTIALLY_VERIFIED` | Nasdaq public endpoint returned cash dividends, including `$0.15` ex-date 2026-07-06; Micron's official Q3 release also states the declaration. |
| Splits | `NOT_VERIFIED` | A tested Nasdaq website split path returned 404; Alpha Vantage documents split data but no key/entitlement was available. Nasdaq states its dividend history is not adjusted for splits. |

Retrieval time for the repeatable probe: approximately 2026-07-11 20:25 +08:00. The price is a real response observed during feasibility work, not a licensed production feed or valuation conclusion.

## SEC endpoint-by-endpoint result

Final probe request format:

```text
Method: GET
User-Agent: StockResearchAgent-Feasibility/0.1 contact=USER_CONTACT_NOT_CONFIGURED purpose=personal-read-only-research
Accept: application/json, text/plain, */*   # JSON endpoints
Accept: text/html                           # filing documents
Accept-Encoding: identity
```

`USER_CONTACT_NOT_CONFIGURED` is an honest placeholder, not a compliant production contact. The production format must be:

```text
StockResearchAgent/<version> contact=<USER_CONFIGURED_REAL_EMAIL_OR_URL> purpose=<short-purpose>
```

No real person/company contact is fabricated in Stage 1; it remains user-supplied configuration.

| Endpoint type | URL | Final result | Interpretation |
|---|---|---|---|
| Submissions | `https://data.sec.gov/submissions/CIK0000723125.json` | HTTP 200, JSON parsed | Available in the current environment with the stated placeholder User-Agent. Returned MU identity and 10-K/10-Q/8-K metadata. |
| Company Facts | `https://data.sec.gov/api/xbrl/companyfacts/CIK0000723125.json` | HTTP 200, JSON parsed | Available in the current environment; selected USD concepts parsed. |
| Filing index | `https://www.sec.gov/Archives/edgar/data/723125/000072312526000015/index.json` | Python `urllib`: HTTP 403; .NET `HttpClient` retry: HTTP 200, valid JSON, 83 items | Client/time-sensitive and therefore only `PARTIALLY_VERIFIED`. The 403 response used the undeclared-automated-tool page; the 200 response proved that this specific index can be retrieved, but not reliably under the current placeholder configuration. |
| 2026 Q3 10-Q document | `https://www.sec.gov/Archives/edgar/data/723125/000072312526000015/mu-20260528.htm` | HTTP 403, `text/html` | Same undeclared-automated-tool response. |
| FY2025 10-K document | `https://www.sec.gov/Archives/edgar/data/723125/000072312525000028/mu-20250828.htm` | HTTP 403, `text/html` | Same undeclared-automated-tool response. |

The 403 is not observed on `data.sec.gov` submissions or Company Facts. It is stable for both tested `www.sec.gov/Archives/edgar/...` primary documents and intermittent/client-sensitive for the tested filing index. This does not prove that every non-Archive SEC path works. A real contact, conservative request policy and repeatable replay are still required.

## Unverified items

- Licensed U.S. EOD provider for persistent caching and report display.
- Full split history and exact adjustment factors from an authorized API.
- Completeness of SEC Company Facts for every metric and every historical restatement.
- A stable mapping policy for custom tags across filing versions.
- A compliant real-contact SEC User-Agent and repeatable Archive index/document replay across the chosen production client.
- Rights to cache or redistribute issuer IR materials beyond personal research.

## Data gaps and risks

1. Company Facts includes standardized facts, but custom tags and dimensions require filing-level inspection.
2. Duplicate contexts, amended filings and different duration facts can produce multiple candidate values.
3. Fiscal quarters are week-based and cannot be grouped by calendar year.
4. Nasdaq's public website endpoint has no established API SLA or license for the planned application.
5. SEC currently classifies the placeholder-contact Archive traffic as an undeclared automated tool and returns 403. A real contact, declared traffic, low internal limit, bulk/cache preference and backoff are required.

## Required before formal integration

- Select a licensed U.S. EOD/corporate-actions provider or obtain suitable Nasdaq Data Link terms.
- Implement SEC requests with a real contact in User-Agent, less than the published 10 requests/second ceiling, lower internal limits, backoff and cache.
- Build a deterministic context-selection rule using accession, filed date, form, period start/end, fiscal year/period, frame, unit and amendment state.
- Reconcile Company Facts against the filing's Inline XBRL and presentation tables.
- Validate a dividend and a historical split end to end before adjusted-price support is accepted.
