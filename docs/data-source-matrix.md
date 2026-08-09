# Data Source Feasibility Matrix

Assessment date: 2026-07-11. `VERIFIED` means this environment obtained the stated minimal result or an official contract page explicitly confirms it. It does not imply that every field, entitlement or production SLA is verified.

## Coverage by required data type

| # | Data type | Preferred V0.1 source | Backup/cross-check | Validation status | Decision |
|---:|---|---|---|---|---|
| 1 | A-share security master | Licensed Tushare Pro or SSE-authorized reference feed; official SSE pages for evidence | SSE suggestion file | `PARTIALLY_VERIFIED` | SSE returned `601138/工业富联`, but active-status history and reuse contract are unresolved. |
| 2 | U.S. security master | SEC company tickers + submissions; licensed Nasdaq reference data for market fields | Issuer IR | `VERIFIED` for MU | SEC returned MU/CIK/exchange; SEC's ticker file returned 403 in one probe, so submissions is the verified MU path. |
| 3 | A-share calendar | SSE annual closure notices and rules | Tushare calendar after authentication | `VERIFIED` for official 2026 notices | Annual notices are human-readable; machine normalization is later work. |
| 4 | U.S. calendar | Nasdaq/NYSE official holiday pages | Maintained exchange-calendar library, checked against official notices | `VERIFIED` for published calendar | Early closes and emergency closures still require updates. |
| 5 | A-share daily prices | Licensed Tushare or SSE-authorized EOD feed | SSE public website endpoint for cross-check only | `PARTIALLY_VERIFIED` | Public endpoint returned 601138 bars but lacks a public API/license/SLA. |
| 6 | U.S. daily prices | Licensed Nasdaq Data Link EOD/Bars or Alpha Vantage under suitable terms | Nasdaq public site for cross-check only | `PARTIALLY_VERIFIED` | MU OHLCV was returned; production entitlement was not. |
| 7 | A-share adjustment factors | Tushare `adj_factor` after authentication | Authorized commercial provider | `NOT_VERIFIED` | Capability is documented; no token or event-level validation. |
| 8 | U.S. splits and dividends | Licensed market-data/corporate-action feed | SEC filings + issuer IR + Nasdaq page | `PARTIALLY_VERIFIED` | Dividends verified; split path not verified. |
| 9 | A-share three statements | Authenticated Tushare or licensed Wind/Choice-class provider, reconciled to official PDF | Official PDF parsing for evidence only | `NOT_VERIFIED` | PDFs accessible; structured provider not connected. |
| 10 | U.S. three statements | SEC Inline XBRL + Company Facts | Micron IR filing mirror | `PARTIALLY_VERIFIED` for MU | Company Facts returned core statement concepts, but filing-level reconciliation is blocked by the tested Archive 403 and deterministic context/restatement handling remains to implement. |
| 11 | A-share financial metrics | Compute internally from normalized statements | Provider metrics only as cross-check | `NOT_VERIFIED` | Do not treat provider-calculated metrics as canonical. |
| 12 | U.S. XBRL | SEC Company Facts + filing Inline XBRL | SEC nightly bulk ZIP | `PARTIALLY_VERIFIED` | Company Facts is verified. Earlier isolated access observed MU custom tags, but the final standardized Archive document probes returned 403, so filing-level custom-tag access is not currently reproducible. |
| 13 | A-share announcements/reports | SSE and CNINFO official disclosure platforms | Company IR | `VERIFIED` for SSE 601138 documents | Public query interface is undocumented; caching/display rights unresolved. |
| 14 | SEC 10-K/10-Q/8-K | SEC submissions and Archives | Micron IR mirror | `PARTIALLY_VERIFIED` | Submissions verified forms/accessions. The Archive index was client-sensitive (Python 403; .NET retry 200 with 83 valid JSON items), while both primary documents remained 403. No repeatable complete filing chain is claimed. |
| 15 | Issuer IR materials | Industrial FII and Micron official IR domains | Exchange/SEC filed exhibits | `PARTIALLY_VERIFIED` | Micron IR tested; Industrial FII IR automation and reuse terms not tested. |
| 16 | Corporate actions | Licensed provider plus official announcements | SEC/issuer/SSE pages | `PARTIALLY_VERIFIED` | MU dividends and FII dividend/share disclosures observed; normalized complete history absent. |
| 17 | Industry/competition | Company filings, regulator/government statistics, named industry associations | Licensed research databases | `NOT_VERIFIED` | No single complete source; every fact requires source-specific review. |
| 18 | Consensus estimates (future) | LSEG/FactSet/Bloomberg/Wind/Choice or another licensed estimates product | None acceptable without license | `NOT_SUITABLE` for V0.1 | Deferred and explicitly out of scope; pricing, history and redistribution require vendor quotes/contracts. |

## Candidate source records

Every candidate below uses the required due-diligence fields. Unknown permissions are deliberately `NOT_VERIFIED`.

### DS-01 — Shanghai Stock Exchange public website and website JSON/JSONP

| Field | Finding |
|---|---|
| Data type | A-share master evidence, trading calendar, daily website bars, announcements, periodic reports, company actions/pages |
| Source name | Shanghai Stock Exchange (`sse.com.cn`, `query.sse.com.cn`, `yunhq.sse.com.cn`) |
| Official/non-official | Official exchange website |
| Interface/access | HTML/PDF and dynamic website endpoints; no production API contract discovered for the probed JSON/JSONP paths |
| API key | No for the tested public pages |
| Paid / free quota | Public pages are viewable; an API quota was not published — `NOT_VERIFIED` |
| Rate limit | `NOT_VERIFIED`; feasibility probes used low frequency and timeout |
| Update frequency | Trading rules/status pages and announcements are event-driven; website daily bar showed 2026-07-10 — API schedule `NOT_VERIFIED` |
| Historical coverage | Website bar response reported total 1,962 for 601138; general guarantees `NOT_VERIFIED` |
| Field completeness | Identity name/code, bar arrays and announcement metadata observed; active-status history and documented bar schema incomplete |
| Adjusted data | No adjustment factor observed |
| Filing versions | PDFs/announcement dates available; structured restatement identifiers not verified |
| Historical as-of query | Date filters exist for announcements and bars; guarantee `NOT_VERIFIED` |
| Cache / display / redistribution / commercial use | All `NOT_VERIFIED` for website endpoints; SSEInfo states exchange information use/operation requires permission |
| Stability | Official site, but dynamic endpoints are undocumented and one company-list query returned a system-busy error |
| Main risk | Treating a website backend as a licensed production API |
| Backup | Tushare or SSEInfo licensed feed; CNINFO for disclosure cross-check |
| Validation status | `PARTIALLY_VERIFIED` |
| Evidence | [SSE stock pages](https://www.sse.com.cn/assortment/stock/), [2026 closure schedule](https://www.sse.com.cn/disclosure/dealinstruc/closed/), [SSEInfo authorization statement](https://www.sseinfo.com/aboutus/authstatement/), local probe output |

### DS-02 — SSEInfo licensed market-data services

| Field | Finding |
|---|---|
| Data type | Official Level-1/Level-2 market data, reference/intelligent data and licensing |
| Source name | 上证所信息网络有限公司 |
| Official/non-official | Officially authorized exchange information operator |
| Interface/access | Licensed feeds, gateways/clients and data services; application required |
| API key | Contract/technical credentials likely; exact mechanism `NOT_VERIFIED` |
| Paid / free quota / rate | Paid license path; exact V0.1 quote, quota and limits `NOT_VERIFIED` |
| Update frequency | Realtime/market-feed products; EOD entitlement specifics require quote |
| Historical coverage / fields / adjustment / filing versions / as-of | Product-specific, all `NOT_VERIFIED` pending proposal |
| Cache / display / redistribution / commercial use | Explicitly license-managed; permitted scope must be written into the contract |
| Stability | Exchange-authorized; production suitability expected but not tested |
| Main risk | Cost and contractual overhead may be disproportionate for personal V0.1 |
| Backup | Tushare personal license for prototype only |
| Validation status | `PARTIALLY_VERIFIED` (official service and license requirement confirmed; access not tested) |
| Evidence | [Market-data services](https://www.sseinfo.com/services/assortment/market/), [authorization statement](https://www.sseinfo.com/aboutus/authstatement/) |

### DS-03 — CNINFO

| Field | Finding |
|---|---|
| Data type | A-share announcements and periodic-report PDFs |
| Source name | 巨潮资讯网 / 深圳证券信息有限公司 |
| Official/non-official | Official statutory disclosure platform operated by a Shenzhen Stock Exchange subsidiary |
| Interface/access | Public website and PDFs; no official public API contract located |
| API key / paid / free quota / rate | Public browsing needs no key; automated API terms, quota and rate all `NOT_VERIFIED` |
| Update frequency | Event-driven disclosure; formal SLA `NOT_VERIFIED` |
| Historical coverage / field completeness | Broad archive visible; exact coverage and API fields `NOT_VERIFIED` |
| Adjusted data | Not applicable |
| Filing versions / historical as-of | Announcement date and PDF identity exist; correction-link semantics require testing |
| Cache / display / redistribution / commercial use | All `NOT_VERIFIED`; public availability is not redistribution permission |
| Stability | Homepage returned 200; one attempted search endpoint returned 500 |
| Main risk | Undocumented anti-bot behavior and unresolved reuse rights |
| Backup | SSE official disclosure for 601138; issuer IR |
| Validation status | `PARTIALLY_VERIFIED` |
| Evidence | [CNINFO disclosure site](https://www.cninfo.com.cn/), [CNINFO description](https://www.cninfo.com.cn/new/disclosure/stock) |

### DS-04 — Tushare Pro

| Field | Finding |
|---|---|
| Data type | A/U.S. master, calendars, daily prices, adjustment factors, A/U.S. statements, indicators, corporate actions, announcements depending on entitlement |
| Source name | Tushare Pro / 北京沃远数据科技有限公司 |
| Official/non-official | Non-exchange commercial/community data provider |
| Interface/access | Token-authenticated REST/SDK |
| API key | Yes, token required |
| Paid / free quota | Official table shows 120 points: 50/minute, 8,000/day, unadjusted A-share daily only, price shown as 0; 2,000+ points: 200/minute and 100,000/day per API, price shown as RMB 200/year for personal users. Endpoint-specific points apply. |
| Rate limit | Official points/frequency table; institution prices are stated as 10x personal in that table |
| Update frequency | Daily docs state trading-day update around 15:00–17:00; endpoint-specific |
| Historical coverage | Daily docs say full history; each endpoint must be checked |
| Field completeness | Broad advertised coverage; sample-provider reconciliation not run |
| Adjusted data | Adjustment factors and adjusted data are advertised |
| Filing versions / historical as-of | Announcement date/report period fields exist; correction/version semantics `NOT_VERIFIED` |
| Cache | `NOT_VERIFIED` in reviewed official terms |
| Display / redistribution | Personal license is non-transferable and for personal viewing; redistribution not authorized by reviewed terms |
| Commercial use | Reviewed agreement grants personal, non-commercial use unless separately agreed |
| Stability | Widely documented, but no authenticated request was possible in this environment |
| Main risk | No token; personal license may not cover future public service; points/standalone entitlements change |
| Backup | Official exchange/SEC documents; paid institutional provider |
| Validation status | `PARTIALLY_VERIFIED` for documentation, `BLOCKED` for actual data access |
| Evidence | [permission/frequency table](https://tushare.pro/document/1?doc_id=290), [API permission list](https://tushare.pro/document/1?doc_id=108), [service agreement](https://tushare.pro/document/1?doc_id=405) |

### DS-05 — AkShare and BaoStock

| Field | Finding |
|---|---|
| Data type | Community wrappers for Chinese security, price, financial and calendar data |
| Source name | AkShare; BaoStock |
| Official/non-official | Non-official open-source/community projects |
| Interface/access | Python packages wrapping upstream sources |
| API key / paid / free quota | Generally package access without a provider key; upstream behavior and quotas are source-specific and `NOT_VERIFIED` |
| Rate/update/history/fields/adjustment/versions/as-of | Not established from a contractual source in this review |
| Cache / display / redistribution / commercial use | Package license does not grant rights to upstream data; all `NOT_VERIFIED` |
| Stability | Vulnerable to upstream HTML/API changes; not tested in this environment |
| Main risk | Conflating open-source client code with lawful/stable data entitlement |
| Backup | Tushare/SSEInfo/official filings |
| Validation status | `NOT_SUITABLE` as sole production source; may be a development cross-check after legal review |
| Evidence | No official provider contract was verified in Stage 1; therefore no quota or license claim is made |

### DS-06 — SEC EDGAR submissions and Company Facts APIs

| Field | Finding |
|---|---|
| Data type | U.S. issuer identity, CIK/ticker/exchange, submissions history and standardized XBRL facts; filing Archive index is DS-07 |
| Source name | U.S. SEC `data.sec.gov` |
| Official/non-official | Official regulator |
| Interface/access | JSON REST endpoints and nightly bulk ZIPs |
| API key / paid / free quota | No authentication or API key; public access. SEC does not state a monetary fee. |
| Rate limit | SEC publishes a maximum of 10 requests/second across EDGAR; project internal limit must be lower |
| Update frequency | Submissions typically under one second and XBRL under one minute after dissemination; bulk files rebuilt nightly, per official API page |
| Historical coverage | Submission and Company Facts histories; older filings can be segmented into additional files |
| Field completeness | Strong for filed data, but not every disclosure has a standard tag; contexts/dimensions can produce duplicates |
| Adjusted data | Not a market-price adjustment source |
| Filing versions | Accession, filing date, form and amendments available |
| Historical as-of | Yes when filtered by filing/publication time; application must enforce it |
| Cache / display / redistribution / commercial use | Technical public access confirmed; rights in issuer filing content and redistribution terms were not fully reviewed — `NOT_VERIFIED` for public product use |
| Stability | Final probe: submissions and Company Facts each returned HTTP 200 on `data.sec.gov`. This does not extend to `www.sec.gov/Archives`, which returned 403. |
| Main risk | Wrong context selection, amendment handling, custom tags and fair-access blocking |
| Backup | SEC bulk ZIP, filing-level Inline XBRL, issuer IR mirror |
| Validation status | `VERIFIED` for MU submissions and Company Facts only; Archive access is separately `BLOCKED`/`PARTIALLY_VERIFIED` |
| Evidence | [EDGAR APIs](https://www.sec.gov/search-filings/edgar-application-programming-interfaces), [rate control](https://www.sec.gov/filergroup/announcements-old/new-rate-control-limits), [company tickers](https://www.sec.gov/file/company-tickers) |

### DS-07 — SEC Archives and Inline XBRL

| Field | Finding |
|---|---|
| Data type | 10-K/10-Q/8-K documents, exhibits, standard/custom XBRL facts and filing presentation |
| Source name | SEC EDGAR Archives |
| Official/non-official | Official regulator archive of issuer submissions |
| Interface/access | HTML, Inline XBRL, XML, XSD, PDF/text exhibits |
| API key / paid | No key; no fee stated |
| Rate limit / update | Same SEC fair-access rules; event-driven upon filing |
| Historical coverage | Long EDGAR history; form-dependent electronic/XBRL coverage |
| Field completeness | Highest-fidelity filing source; custom tags require taxonomy processing |
| Adjusted data | Not applicable |
| Filing versions / as-of | Accession and filed timestamp support version and as-of control |
| Cache/display/redistribution/commercial | `NOT_VERIFIED` for any later public service; personal evidence cache is the intended V0.1 use |
| Stability | The final Python probe returned HTTP 403 for the latest 10-Q `index.json` and both primary HTML documents. A subsequent .NET `HttpClient` GET with the same declared headers returned valid index JSON (HTTP 200, 83 items), while both primary documents still returned 403 with title/H1 `Your Request Originates from an Undeclared Automated Tool`. Access is client/time/configuration sensitive. |
| Main risk | The final User-Agent used `contact=USER_CONTACT_NOT_CONFIGURED`; SEC asked for company-specific identifying information. A real configured contact, conservative rate, caching and bulk use are mandatory. HTML complexity and malicious/untrusted document content remain separate risks. |
| Backup | SEC bulk packages and issuer IR mirrors |
| Validation status | Filing index `PARTIALLY_VERIFIED` but not reproducible; primary 10-Q/10-K documents `BLOCKED`; historical isolated document access is evidence only, not current availability |
| Evidence | [Inline XBRL](https://www.sec.gov/data-research/structured-data/inline-xbrl), [Inline XBRL Viewer guide](https://www.sec.gov/ixviewer/ix.html) |

Final request details for DS-07:

```text
Method: GET
User-Agent: StockResearchAgent-Feasibility/0.1 contact=USER_CONTACT_NOT_CONFIGURED purpose=personal-read-only-research
Accept-Encoding: identity
Index Accept: application/json, text/plain, */*
Document Accept: text/html
```

Tested Archive paths:

- `https://www.sec.gov/Archives/edgar/data/723125/000072312526000015/index.json`
- `https://www.sec.gov/Archives/edgar/data/723125/000072312526000015/mu-20260528.htm`
- `https://www.sec.gov/Archives/edgar/data/723125/000072312525000028/mu-20250828.htm`

The first path produced both 403 (Python `urllib`) and 200/valid JSON (subsequent .NET `HttpClient`); the two primary-document paths produced 403 in both final clients.

Compliant production format: `StockResearchAgent/<version> contact=<USER_CONFIGURED_REAL_EMAIL_OR_URL> purpose=<short-purpose>`. The contact value is a user configuration gap; no fictitious email/name is inserted.

### DS-08 — Micron and Industrial FII investor relations

| Field | Finding |
|---|---|
| Data type | Earnings releases, presentations, prepared remarks, corporate-action statements and filing mirrors |
| Source name | Issuer official IR sites |
| Official/non-official | Official issuer source, but not regulator validation |
| Interface/access | HTML/PDF/event pages; no uniform API |
| API key / paid / quota / rate | No key for tested Micron pages; automation rate and quota `NOT_VERIFIED` |
| Update/history/fields | Event-driven; Micron provides results and presentations; Industrial FII automation not tested |
| Adjusted data / filing versions / historical as-of | Not a price feed; document dates support as-of, but corrections need document-specific checks |
| Cache/display/redistribution/commercial | All `NOT_VERIFIED`; issuer copyright may apply |
| Stability | Micron homepage and Q3 FY2026 materials returned 200 |
| Main risk | Non-GAAP measures, forward-looking statements and mutable web assets |
| Backup | SEC/SSE/CNINFO filed documents |
| Validation status | `PARTIALLY_VERIFIED` |
| Evidence | [Micron Q3 FY2026 release](https://investors.micron.com/news-releases/news-release-details/micron-technology-inc-reports-record-results-third-quarter), [Micron SEC filings](https://investors.micron.com/sec-filings) |

### DS-09 — Nasdaq public Market Activity website

| Field | Finding |
|---|---|
| Data type | U.S. website OHLCV and dividend-history display |
| Source name | Nasdaq Market Activity website/API backend |
| Official/non-official | Official exchange website, but some fields use partners such as QuoteMedia |
| Interface/access | Public website JSON backend; no production API contract established |
| API key / paid / quota / rate | No key for tested calls; all limits and price `NOT_VERIFIED` |
| Update frequency | Website returned current daily rows and dividend events; formal SLA `NOT_VERIFIED` |
| Historical coverage | Queryable website range; guarantee `NOT_VERIFIED` |
| Field completeness | OHLCV observed; dividends observed; tested split path returned 404 |
| Adjusted data | Nasdaq FAQ says dividend history is not adjusted for splits |
| Filing versions / as-of | Not applicable beyond dated rows |
| Cache/display/redistribution/commercial | All `NOT_VERIFIED` for programmatic use |
| Stability | Worked for MU feasibility; parameters changed from common date examples and may change again |
| Main risk | Website scraping/backend use without entitlement; partner data provenance |
| Backup | Licensed Nasdaq Data Link or Alpha Vantage contract |
| Validation status | `PARTIALLY_VERIFIED` |
| Evidence | [Market Activity FAQ](https://www.nasdaq.com/market-activity/mutual-fund/faqsx), local probe output |

### DS-10 — Nasdaq Data Link

| Field | Finding |
|---|---|
| Data type | U.S. reference data, daily/historical/real-time bars, premium EOD data, fundamentals and estimates products |
| Source name | Nasdaq Data Link |
| Official/non-official | Official Nasdaq commercial data platform; some datasets are third-party |
| Interface/access | REST, streaming and tables APIs |
| API key | Account/key required for more than limited free calls and for premium datasets |
| Paid / free quota | Docs state package users without a key are limited to 50 calls/day; EOD U.S. prices are listed as premium. Product price was not visible — `NOT_VERIFIED`. |
| Rate limit | Real-time/delayed REST docs state 100 requests/second; endpoint symbol caps apply. Dataset tables may differ. |
| Update/history/fields | Product-specific; Bars advertises 10+ years and OHLCV; consolidated EOD is advertised |
| Adjusted data / filing versions / as-of | Product-specific, `NOT_VERIFIED` until a dataset contract is chosen |
| Cache/display/redistribution/commercial | Dataset/license-specific; must be quoted and contracted |
| Stability | Commercial official platform; no authenticated subscription tested |
| Main risk | Cost and display/non-display/redistribution entitlements |
| Backup | Alpha Vantage personal license for private prototype; SEC for fundamentals |
| Validation status | `PARTIALLY_VERIFIED` for documentation, `BLOCKED` for subscribed data |
| Evidence | [data organization](https://docs.data.nasdaq.com/docs/data-organization), [API product](https://www.nasdaq.com/solutions/data/nasdaq-data-link/api), [REST rate limits](https://docs.data.nasdaq.com/docs/rate-limits-for-real-timedelayed-rest-api) |

### DS-11 — Alpha Vantage

| Field | Finding |
|---|---|
| Data type | Global daily OHLCV, adjusted daily, corporate actions, statements and ticker search |
| Source name | Alpha Vantage |
| Official/non-official | Independent data provider, not an exchange/regulator |
| Interface/access | API key REST API |
| API key | Yes |
| Paid / free quota | Official premium page states standard limit 25 requests/day; premium plans start at USD 49.99/month for 75 requests/minute, with no daily limit (pricing observed 2026-07-11) |
| Rate limit | Plan-specific 75–1,200 requests/minute in published personal plan table |
| Update/history/fields | Daily API advertises 20+ years; raw daily OHLCV; full history and Daily Adjusted are premium |
| Adjusted data | Daily Adjusted includes adjusted close, splits and dividends |
| Filing versions / historical as-of | Financial endpoint restatement/version semantics `NOT_VERIFIED` |
| Cache / redistribution | `NOT_VERIFIED` in reviewed terms |
| Display / commercial use | Terms grant personal non-commercial use unless agreed in writing; commercial users must contact sales |
| Stability | Documentation verified; no personal key was configured, so MU call was not tested |
| Main risk | Very low free quota, premium adjusted endpoint, and terms ambiguity for any future service |
| Backup | Nasdaq Data Link; SEC for financials |
| Validation status | `PARTIALLY_VERIFIED` for documentation, `BLOCKED` for authenticated data |
| Evidence | [API docs](https://www.alphavantage.co/documentation/), [premium plans](https://www.alphavantage.co/premium/), [terms](https://www.alphavantage.co/terms_of_service/) |

### DS-12 — Official exchange calendars

| Field | Finding |
|---|---|
| Data type | A-share and U.S. trading sessions, holidays and early closes |
| Source name | SSE closure schedule; Nasdaq/NYSE holiday calendars |
| Official/non-official | Official exchanges |
| Interface/access | Human-readable HTML/notices; no common API |
| API key / paid / quota / rate | No key for pages; automated-use limits `NOT_VERIFIED` |
| Update frequency | Annual schedule plus event notices; emergency changes possible |
| Historical coverage | Multiple years shown; long-term guarantee `NOT_VERIFIED` |
| Fields | Holidays and trading hours; timezone/early-close rules must be normalized |
| Adjustment/filing versions | Not applicable; preserve notice publication/version dates |
| Historical as-of | Yes if annual notices are snapshotted by publication date |
| Cache/display/redistribution/commercial | `NOT_VERIFIED` for public products |
| Stability | Official and adequate for calendar-rule evidence |
| Main risk | Emergency closures and rule changes after annual publication |
| Backup | Tested calendar library plus official diff monitoring |
| Validation status | `VERIFIED` for 2026 published schedules |
| Evidence | [SSE closures](https://www.sse.com.cn/disclosure/dealinstruc/closed/), [NYSE hours/calendars](https://www.nyse.com/markets/hours-calendars), [Nasdaq holidays](https://www.nasdaq.com/market-activity/stock-market-holiday-schedule) |

### DS-13 — Commercial terminals and consensus vendors

| Field | Finding |
|---|---|
| Data type | Wind/Choice/LSEG/FactSet/Bloomberg master, market, fundamentals, corporate actions, industry and consensus estimates |
| Source name | Vendor-specific |
| Official/non-official | Commercial aggregators |
| Interface/access | Contracted terminal/API/feed |
| API key / paid / free quota / rate | Account and contract required; all exact figures `NOT_VERIFIED` because no quote or official entitlement document was supplied |
| Update/history/fields/adjustment/versions/as-of | Potentially broad, but product-specific and `NOT_VERIFIED` |
| Cache/display/redistribution/commercial | Contract-specific; commonly material restrictions, all `NOT_VERIFIED` |
| Stability | Potentially production-grade; not tested |
| Main risk | High cost, vendor lock-in and redistribution restrictions |
| Backup | Official filings plus licensed EOD provider; consensus remains unavailable |
| Validation status | `NOT_VERIFIED`; consensus is `NOT_SUITABLE` for V0.1 |
| Evidence | Vendor quote and contract are required; no hearsay limits or prices are recorded |

### DS-14 — Industry and competition evidence

| Field | Finding |
|---|---|
| Data type | Industry structure, demand/supply, competitor disclosures and government statistics |
| Source name | Issuer/competitor filings, official statistics/regulators, identified industry associations |
| Official/non-official | Mixed; source-level classification required |
| Interface/access | Documents/APIs depending on source |
| API key / paid / quota / rate | Source-specific, `NOT_VERIFIED` |
| Update/history/fields | Heterogeneous; no canonical schema |
| Adjustment/filing versions/as-of | Preserve document version, publication time and research cutoff |
| Cache/display/redistribution/commercial | Source-specific; all `NOT_VERIFIED` until selected |
| Stability | Heterogeneous |
| Main risk | Cherry-picking, incompatible definitions and citation drift |
| Backup | Multiple independent primary sources and explicit `UNVERIFIED` gaps |
| Validation status | `NOT_VERIFIED` as a generalized feed |
| Evidence | Source policy is defined in RAG and report documents; no single provider was approved |

## Recommended V0.1 combination

- **A-share documents:** SSE/CNINFO official PDFs, with the public interfaces used only as low-frequency acquisition paths after terms confirmation.
- **A-share structured data:** Tushare personal non-commercial entitlement is the practical prototype candidate, but it remains blocked until a token and caching terms are confirmed; official PDFs remain reconciliation truth.
- **U.S. filings/financials:** SEC submissions, Company Facts and filing Inline XBRL with bulk-cache preference.
- **U.S. daily/corporate actions:** obtain a licensed Alpha Vantage or Nasdaq Data Link entitlement; do not depend on the Nasdaq website backend.
- **Calendars:** official exchange notices normalized locally and tested against a maintained library.
- **Consensus:** no source in V0.1.
