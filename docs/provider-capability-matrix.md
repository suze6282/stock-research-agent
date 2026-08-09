# Provider Capability and License Matrix

Status: Stage 9 approved implementation register
Reviewed on: 2026-08-01
Evidence rule: only official provider documentation or formal developer documentation is used.

This document is a design-time register. It does not authorize a Live request. A
Provider may be implemented as an offline contract while its production status
remains `BLOCKED`. Any unknown critical license field is recorded as
`UNKNOWN_REQUIRES_REVIEW` and prevents production ingestion.

## Status vocabulary

- `PASS`: the capability or property is established by an official source.
- `PARTIAL`: only part of the capability is established.
- `BLOCKED`: the capability must not be used in production.
- `NOT_ATTEMPTED`: no Live request was made.
- `UNKNOWN_REQUIRES_REVIEW`: the official material reviewed does not establish the
  required right or contract.
- `APPROVED_FOR_CONTROLLED_LIVE`: engineering and public-use rules are sufficiently
  clear for a separately approved, finite Live validation. This is not a record that
  the validation ran.
- `RESTRICTED_PERSONAL_NONCOMMERCIAL`: the reviewed terms grant a personal,
  non-transferable, non-commercial license only.

## Official-source register

| Source ID | Official source | Design evidence |
|---|---|---|
| SEC-API | https://www.sec.gov/search-filings/edgar-application-programming-interfaces | Submissions and XBRL Company Facts are unauthenticated JSON APIs; 10-digit zero-padded CIK; bulk archives; update behavior. |
| SEC-ARCHIVE | https://www.sec.gov/search-filings/edgar-search-assistance/accessing-edgar-data | Archive directory, accession-number and filing-document path rules; filing index and complete-submission distinctions. |
| SEC-FAQ | https://www.sec.gov/about/webmaster-frequently-asked-questions | Declared User-Agent format, maximum 10 requests/second, scripted access, public filing reuse statement. |
| SEC-RATE | https://www.sec.gov/filergroup/announcements-old/new-rate-control-limits | Aggregate maximum of 10 requests/second regardless of machines; temporary restriction behavior. |
| TUSHARE-PERM | https://tushare.pro/document/1?doc_id=290 | Points-based and separately granted capabilities; per-minute and daily entitlement tiers. |
| TUSHARE-API-LIST | https://tushare.pro/document/1?doc_id=108 | Official capability list and minimum entitlement levels. |
| TUSHARE-TERMS | https://tushare.pro/document/1?doc_id=405 | Personal, non-transferable, non-commercial, revocable, time-limited use; Token protection and official-channel requirements. |
| TUSHARE-HTTP | https://tushare.pro/document/2?doc_id=130 | POST request/response contract; Token in request body; documented endpoint example uses HTTP rather than an approved HTTPS REST endpoint. |
| TUSHARE-STOCK | https://tushare.pro/document/1?doc_id=25 | `stock_basic` schema, row bound and entitlement. |
| TUSHARE-CALENDAR | https://tushare.pro/document/2?doc_id=26 | `trade_cal` schema and entitlement. |
| TUSHARE-DAILY | https://tushare.pro/document/1?doc_id=27 | `daily` schema, update window, row/request guidance and units. |
| TUSHARE-CASHFLOW | https://tushare.pro/document/2?doc_id=44 | `cashflow` schema, revisions/report types and entitlement. |
| TUSHARE-INDICATOR | https://tushare.pro/document/2?doc_id=79 | `fina_indicator` schema, bounded records and entitlement. |
| TUSHARE-DISCLOSURE | https://tushare.pro/document/2?doc_id=162 | `disclosure_date` metadata schema and entitlement. |
| SZSE-INTERFACE | https://www.szse.cn/marketServices/technicalservice/interface/index.html | Formal exchange interface documents exist, primarily for market participants; no public disclosure-body API or storage license was established. |
| SSE-INTERFACE | https://www.sse.com.cn/services/tradingtech/data/ | Formal exchange technical interfaces exist for market participants; no public disclosure-body API or storage license was established. |
| CNINFO-SITE | https://www.cninfo.com.cn/new/fulltextSearch | CNINFO identifies itself as a statutory disclosure platform and exposes a data-service entry; no production API contract, automation limit, retention, caching or redistribution grant was established. |

The sources above were reviewed without calling a data endpoint, using a credential,
downloading a filing, or scraping an A-share disclosure site.

## Candidate Provider summary

The source IDs in the tables below are the value set for
`official_documentation_source`. The complete persisted/exported matrix contract is:
`provider_code`, `provider_name`, `provider_type`,
`official_documentation_source`, `supported_markets`,
`supported_security_types`, `supported_data_domains`, `authentication_type`,
`credential_required`, `credential_reference_name`, `rate_limit_source`,
`request_identification_requirement`, `allowed_endpoints`,
`raw_payload_retention`, `normalized_data_retention`,
`redistribution_allowed`, `cache_allowed`, `retention_limit`,
`attribution_required`, `terms_version`, `provider_version`,
`incremental_sync_supported`, `historical_backfill_supported`,
`checkpoint_supported`, `live_test_status`, `production_status` and
`blocked_reason`. The human-readable tables split this wide contract by concern
without omitting a field.

| provider_code | provider_name | provider_type | supported_markets | supported_security_types | supported_data_domains | production_status | live_test_status | blocked_reason |
|---|---|---|---|---|---|---|---|---|
| `SEC_EDGAR_PUBLIC_V1` | SEC EDGAR public data and filing archive | `US_SEC_FILINGS` | US public issuers filing with SEC | Common stock issuer filings and other CIK-scoped filers; Stage 9 reference scope is Micron | Security/issuer metadata, filing metadata, Company Facts, filing index, primary document, exhibits by explicit policy | `CONDITIONAL` | `NOT_ATTEMPTED` | Requires a real contact identity, exact host/path policy, explicit finite Live approval and successful validation. |
| `TUSHARE_PRO_V1` | Tushare Pro structured A-share data | `A_SHARE_STRUCTURED_DATA` | China A-share | Common stock in the approved endpoint scope | Security master, calendar, EOD prices, statements, indicators, corporate actions, disclosure metadata | `BLOCKED` | `NOT_ATTEMPTED` | Current Token entitlement is unknown; terms are personal/non-commercial; raw/cache/derived rights are not explicit; approved HTTPS REST endpoint is not established by the reviewed REST document. |
| `SSE_DISCLOSURE_V1_CANDIDATE` | Shanghai Stock Exchange disclosure source | `A_SHARE_DISCLOSURE_DOCUMENTS` | Shanghai | Exchange-listed securities | Disclosure metadata and official bodies, subject to an approved contract | `BLOCKED` | `NOT_ATTEMPTED` | Public automation API, rate, raw retention, caching and redistribution rights remain unknown. |
| `SZSE_DISCLOSURE_V1_CANDIDATE` | Shenzhen Stock Exchange disclosure source | `A_SHARE_DISCLOSURE_DOCUMENTS` | Shenzhen | Exchange-listed securities | Disclosure metadata and official bodies, subject to an approved contract | `BLOCKED` | `NOT_ATTEMPTED` | Reviewed technical interfaces do not establish a public production disclosure-body contract or storage license. |
| `CNINFO_DISCLOSURE_V1_CANDIDATE` | CNINFO disclosure/data service candidate | `A_SHARE_DISCLOSURE_DOCUMENTS` | China public markets represented by CNINFO | Listed securities represented by an approved service contract | Disclosure metadata and official bodies, subject to a signed/official API contract | `BLOCKED` | `NOT_ATTEMPTED` | No approved API contract, automation rule, pricing, retention, caching, excerpt or redistribution grant has been obtained. |
| `LICENSED_US_EOD_UNSELECTED` | Licensed U.S. EOD Provider, vendor unselected | `US_EOD_MARKET_DATA` | US equity | Common stock after vendor selection | EOD OHLCV, adjustments and corporate actions only if licensed | `BLOCKED` | `NOT_ATTEMPTED` | No vendor, commercial terms, credentials, endpoint or license has been selected. |
| `PRODUCTION_EMBEDDING_UNSELECTED` | Production Embedding Provider, vendor unselected | `PRODUCTION_EMBEDDING` | Not market-specific | Text chunks only | Embedding generation | `BLOCKED` | `NOT_ATTEMPTED` | No provider, cost, data-processing terms, region, credential or model version has been approved. |
| `STAGE1_OFFLINE_FIXTURES` | Existing Stage 1-derived safe crops | `FIXTURE` | CN A-share and US equity samples | `601138.SH`, `MU` | Limited daily-price and SEC metadata test evidence | `TEST_ONLY` | `NOT_LIVE` | Explicitly `FIXTURE`, `OFFLINE`, `NOT_LIVE`; never a production or Live qualification. |

## Authentication, request identity and endpoint matrix

| provider_code | authentication_type | credential_required | credential_reference_name | request_identification_requirement | allowed_endpoints | rate_limit_source |
|---|---|---|---|---|---|---|
| `SEC_EDGAR_PUBLIC_V1` | `NONE` plus declared contact identity | No API key; yes for configured contact identity | `SEC_EDGAR_CONTACT_IDENTITY` | User-Agent containing application/company identity and real contact address | Exact HTTPS hosts `data.sec.gov` and `www.sec.gov`; exact templates `/submissions/CIK##########.json`, `/api/xbrl/companyfacts/CIK##########.json`, and `/Archives/edgar/data/{validated_cik}/{validated_accession_without_dashes}/{validated_document_path}` | SEC-FAQ and SEC-RATE; control-plane policy must remain at or below the current official aggregate ceiling and use a more conservative project rate. |
| `TUSHARE_PRO_V1` | `API_TOKEN` | Yes | `TUSHARE_PRO_TOKEN` | Token must be resolved only inside the executor and never logged, persisted or exposed | No production endpoint approved at design time. Endpoint identity must be fixed after official HTTPS REST confirmation; callers cannot supply URLs. | TUSHARE-PERM plus each endpoint document; actual Token entitlement must be checked explicitly. |
| `SSE_DISCLOSURE_V1_CANDIDATE` | `UNKNOWN_REQUIRES_REVIEW` | `UNKNOWN_REQUIRES_REVIEW` | None approved | `UNKNOWN_REQUIRES_REVIEW` | None approved | `UNKNOWN_REQUIRES_REVIEW` |
| `SZSE_DISCLOSURE_V1_CANDIDATE` | `UNKNOWN_REQUIRES_REVIEW` | `UNKNOWN_REQUIRES_REVIEW` | None approved | `UNKNOWN_REQUIRES_REVIEW` | None approved | `UNKNOWN_REQUIRES_REVIEW` |
| `CNINFO_DISCLOSURE_V1_CANDIDATE` | `UNKNOWN_REQUIRES_REVIEW` | `UNKNOWN_REQUIRES_REVIEW` | None approved | `UNKNOWN_REQUIRES_REVIEW` | None approved | `UNKNOWN_REQUIRES_REVIEW` |
| `LICENSED_US_EOD_UNSELECTED` | `UNKNOWN_REQUIRES_REVIEW` | Yes after selection | None approved | Vendor contract required | None approved | `UNKNOWN_REQUIRES_REVIEW` |
| `PRODUCTION_EMBEDDING_UNSELECTED` | `UNKNOWN_REQUIRES_REVIEW` | Yes after selection | None approved | Vendor contract required | None approved | `UNKNOWN_REQUIRES_REVIEW` |
| `STAGE1_OFFLINE_FIXTURES` | `NONE` | No | None | Not applicable | Package resources only; no network endpoint | Not applicable |

## Capability matrix

| provider_code | operation | market | supports_incremental | supports_backfill | supports_as_of | supports_revisions | supports_raw_payload | status and evidence |
|---|---|---|---:|---:|---:|---:|---:|---|
| `SEC_EDGAR_PUBLIC_V1` | `FETCH_SEC_SUBMISSIONS` | US | Yes, using recent filings plus linked history files and an accession checkpoint | Yes | Yes, using acceptance/filed timestamps and strict publication cutoffs | Yes | Yes | `CONDITIONAL`; SEC-API. |
| `SEC_EDGAR_PUBLIC_V1` | `FETCH_FINANCIAL_STATEMENTS` | US | Yes, with accession/fact identity and explicit restatement handling | Yes | Yes | Yes | Yes | `CONDITIONAL`; Company Facts is structured fact evidence, not filing body evidence. |
| `SEC_EDGAR_PUBLIC_V1` | `FETCH_SEC_FILING_DOCUMENT` | US | Yes, by accession and validated document path | Yes | Yes | Yes; new accession/document bytes produce new immutable versions | Yes | `CONDITIONAL`; SEC-ARCHIVE. |
| `TUSHARE_PRO_V1` | `FETCH_SECURITY_MASTER` | CN A-share | Yes, by provider update/listing state after contract approval | Yes | Partial; historical visibility depends on fields supplied | Yes | Contract-dependent | Offline contract `PASS`; production `BLOCKED`. |
| `TUSHARE_PRO_V1` | `FETCH_MARKET_CALENDAR` | CN A-share | Yes, bounded date windows | Yes | Yes | Provider-dependent | Contract-dependent | Offline contract `PASS`; production `BLOCKED`. |
| `TUSHARE_PRO_V1` | `FETCH_EOD_PRICES` | CN A-share | Yes, by trading date | Yes | Yes | Provider-dependent | Contract-dependent | Offline contract `PASS`; production `BLOCKED`. |
| `TUSHARE_PRO_V1` | `FETCH_FINANCIAL_STATEMENTS` | CN A-share | Yes, using announcement/report period/update identity | Yes | Yes only when publication fields are present | Yes; report/update types must be retained | Contract-dependent | Offline contract `PASS`; production `BLOCKED`. |
| `TUSHARE_PRO_V1` | `FETCH_FINANCIAL_METRICS` | CN A-share | Yes | Yes | Yes only when publication fields are present | Yes | Contract-dependent | Provider metrics stay provider facts; they do not bypass Stage 5 formula/version rules. |
| `TUSHARE_PRO_V1` | `FETCH_CORPORATE_ACTIONS` | CN A-share | Yes | Yes | Yes only with announcement/effective dates | Yes | Contract-dependent | Capability documented; production `BLOCKED`. |
| `TUSHARE_PRO_V1` | `FETCH_DISCLOSURE_METADATA` | CN A-share | Yes | Yes | Yes when actual publication metadata is present | Yes | Contract-dependent | Metadata is never treated as a document body. |
| `SSE_DISCLOSURE_V1_CANDIDATE` | `FETCH_DISCLOSURE_DOCUMENT` | Shanghai | Unknown | Unknown | Unknown | Unknown | Unknown | `BLOCKED`; an approved public/contracted API and storage terms are absent. |
| `SZSE_DISCLOSURE_V1_CANDIDATE` | `FETCH_DISCLOSURE_DOCUMENT` | Shenzhen | Unknown | Unknown | Unknown | Unknown | Unknown | `BLOCKED`; formal participant interface material is not a public production grant. |
| `CNINFO_DISCLOSURE_V1_CANDIDATE` | `FETCH_DISCLOSURE_DOCUMENT` | CN public markets | Unknown | Unknown | Unknown | Unknown | Unknown | `BLOCKED`; service contract required. |
| `LICENSED_US_EOD_UNSELECTED` | `FETCH_EOD_PRICES` | US | Unknown | Unknown | Unknown | Unknown | Unknown | `BLOCKED` until vendor selection and license approval. |
| `PRODUCTION_EMBEDDING_UNSELECTED` | `GENERATE_EMBEDDING` | Not applicable | Unknown | Unknown | Version-bound input only | Model versions required | No source-document raw retention through this capability | `BLOCKED`; Stage 9 does not call a model or embedding service. |

## License and data-handling matrix

| provider_code | raw_payload_retention | normalized_data_retention | redistribution_allowed | cache_allowed | retention_limit | attribution_required | commercial_use_status | derived_data_status | license status |
|---|---|---|---|---|---|---|---|---|---|
| `SEC_EDGAR_PUBLIC_V1` | Allowed for government-created and public filing content, subject to fair-access/security policy and per-artifact content review | Allowed | Official FAQ says government-created and EDGAR public filing content are free to access and reuse; third-party material embedded in a filing must still be treated conservatively | Allowed for public filing/API content; validators should be honored | No limit established in reviewed official material | Declared request identity is required for automation; source attribution is required by project evidence policy | Public reuse permitted by SEC-FAQ | Allowed, with source lineage | `APPROVED` for controlled public-content use; Live remains separately gated. |
| `TUSHARE_PRO_V1` | `UNKNOWN_REQUIRES_REVIEW` | `UNKNOWN_REQUIRES_REVIEW` beyond personal viewing | No grant established; account/service is personal and non-transferable | `UNKNOWN_REQUIRES_REVIEW` | Service entitlement is time-limited; retained-data period not established | `UNKNOWN_REQUIRES_REVIEW` | `RESTRICTED_PERSONAL_NONCOMMERCIAL` | `UNKNOWN_REQUIRES_REVIEW` | `RESTRICTED`; production writes and Live requests remain blocked. |
| `SSE_DISCLOSURE_V1_CANDIDATE` | `UNKNOWN_REQUIRES_REVIEW` | `UNKNOWN_REQUIRES_REVIEW` | `UNKNOWN_REQUIRES_REVIEW` | `UNKNOWN_REQUIRES_REVIEW` | `UNKNOWN_REQUIRES_REVIEW` | `UNKNOWN_REQUIRES_REVIEW` | `UNKNOWN_REQUIRES_REVIEW` | `UNKNOWN_REQUIRES_REVIEW` | `UNKNOWN`; production blocked. |
| `SZSE_DISCLOSURE_V1_CANDIDATE` | `UNKNOWN_REQUIRES_REVIEW` | `UNKNOWN_REQUIRES_REVIEW` | `UNKNOWN_REQUIRES_REVIEW` | `UNKNOWN_REQUIRES_REVIEW` | `UNKNOWN_REQUIRES_REVIEW` | `UNKNOWN_REQUIRES_REVIEW` | `UNKNOWN_REQUIRES_REVIEW` | `UNKNOWN_REQUIRES_REVIEW` | `UNKNOWN`; production blocked. |
| `CNINFO_DISCLOSURE_V1_CANDIDATE` | `UNKNOWN_REQUIRES_REVIEW` | `UNKNOWN_REQUIRES_REVIEW` | `UNKNOWN_REQUIRES_REVIEW` | `UNKNOWN_REQUIRES_REVIEW` | `UNKNOWN_REQUIRES_REVIEW` | `UNKNOWN_REQUIRES_REVIEW` | `UNKNOWN_REQUIRES_REVIEW` | `UNKNOWN_REQUIRES_REVIEW` | `UNKNOWN`; production blocked. |
| `LICENSED_US_EOD_UNSELECTED` | `UNKNOWN_REQUIRES_REVIEW` | `UNKNOWN_REQUIRES_REVIEW` | `UNKNOWN_REQUIRES_REVIEW` | `UNKNOWN_REQUIRES_REVIEW` | `UNKNOWN_REQUIRES_REVIEW` | `UNKNOWN_REQUIRES_REVIEW` | `UNKNOWN_REQUIRES_REVIEW` | `UNKNOWN_REQUIRES_REVIEW` | `BLOCKED`; vendor unselected. |
| `PRODUCTION_EMBEDDING_UNSELECTED` | Source text must not be sent until data-processing terms approve it | Vector retention unknown | Unknown | Unknown | Unknown | Unknown | Unknown | Unknown | `BLOCKED`; vendor unselected. |
| `STAGE1_OFFLINE_FIXTURES` | Only exact safe crops already in Git, governed by their manifests | Only test/fixture projections | No production redistribution claim | Package-local only | Project test lifetime | Manifest/source label required | Personal offline research only | Test-only | `TEST_ONLY`. |

## Version and synchronization matrix

| provider_code | terms_version | provider_version | incremental_sync_supported | historical_backfill_supported | checkpoint_supported | current decision |
|---|---|---|---:|---:|---:|---|
| `SEC_EDGAR_PUBLIC_V1` | URLs plus SHA-256 of reviewed policy material captured when approved; reviewed 2026-07-29 | Proposed adapter `1.0.0` | Yes | Yes | Yes: CIK + form filter + acceptance timestamp + accession + document path/checksum | Recommended P1 reference adapter after design approval; Live requires separate finite approval. |
| `TUSHARE_PRO_V1` | Service agreement and permission pages reviewed 2026-07-29; mutable terms require re-review before each production enablement | Proposed adapter `1.0.0` | Yes by endpoint-specific watermark | Yes, entitlement-dependent | Yes: endpoint + security/universe + date/period + provider record identity | Build offline contract after design approval; production Live remains blocked until license, HTTPS REST and entitlement are approved. |
| `SSE_DISCLOSURE_V1_CANDIDATE` | `UNKNOWN_REQUIRES_REVIEW` | No adapter approved | Unknown | Unknown | Unknown | Contract only; no implementation that sends requests. |
| `SZSE_DISCLOSURE_V1_CANDIDATE` | `UNKNOWN_REQUIRES_REVIEW` | No adapter approved | Unknown | Unknown | Unknown | Contract only; no implementation that sends requests. |
| `CNINFO_DISCLOSURE_V1_CANDIDATE` | `UNKNOWN_REQUIRES_REVIEW` | No adapter approved | Unknown | Unknown | Unknown | Contract only; no implementation that sends requests. |
| `LICENSED_US_EOD_UNSELECTED` | Unknown | No adapter approved | Unknown | Unknown | Unknown | Generic port and `BLOCKED` definition only. |
| `PRODUCTION_EMBEDDING_UNSELECTED` | Unknown | No adapter approved | Unknown | Unknown | Unknown | Generic governance record only; no model call. |
| `STAGE1_OFFLINE_FIXTURES` | Per-fixture manifest | Existing fixture adapters `1.0.0` | No | No | Idempotency only | Remains isolated and never upgraded to Live status. |

## Tushare endpoint qualification

The following endpoint contracts may be implemented against synthetic or legally
retained minimal fixtures after design approval. This table is not permission to use
a Token.

| Endpoint | Domain | Required identity and watermark | Official entitlement evidence | Production decision |
|---|---|---|---|---|
| `stock_basic` | Security master | `ts_code`, listing state and provider update observation | TUSHARE-STOCK and TUSHARE-PERM | `BLOCKED_PROVIDER_LICENSE_AND_ENTITLEMENT` |
| `trade_cal` | Market calendar | exchange + bounded calendar window | TUSHARE-CALENDAR | `BLOCKED_PROVIDER_LICENSE_AND_ENTITLEMENT` |
| `daily` | Unadjusted EOD | `ts_code` + `trade_date`; store exact provider units | TUSHARE-DAILY | `BLOCKED_PROVIDER_LICENSE_AND_ENTITLEMENT` |
| `income` | Provider financial facts | `ts_code`, announcement date, period, report/update type | TUSHARE-API-LIST | `BLOCKED_PROVIDER_LICENSE_AND_ENTITLEMENT` |
| `balancesheet` | Provider financial facts | same identity discipline as statements | TUSHARE-API-LIST | `BLOCKED_PROVIDER_LICENSE_AND_ENTITLEMENT` |
| `cashflow` | Provider financial facts | `ts_code`, announcement dates, period, report/update type | TUSHARE-CASHFLOW | `BLOCKED_PROVIDER_LICENSE_AND_ENTITLEMENT` |
| `fina_indicator` | Provider-computed metrics | `ts_code`, announcement date, period; never replace Stage 5 formulas | TUSHARE-INDICATOR | `BLOCKED_PROVIDER_LICENSE_AND_ENTITLEMENT` |
| `dividend` | Corporate actions | provider record identity plus announcement/record/ex/effective dates | TUSHARE-API-LIST | `BLOCKED_PROVIDER_LICENSE_AND_ENTITLEMENT` |
| `disclosure_date` | Disclosure metadata | `ts_code`, reporting period, plan/actual/modified dates | TUSHARE-DISCLOSURE | `BLOCKED_PROVIDER_LICENSE_AND_ENTITLEMENT`; never body evidence |

An entitlement error such as the documented permission response must map to
`BLOCKED_PROVIDER_ENTITLEMENT`, must not be retried, and must not open a generic
availability incident unless policy explicitly classifies it.

## Approval conditions

### SEC limited Live validation

Before the first request, the operator must present and obtain approval for:

- `SEC_EDGAR_CONTACT_IDENTITY` configuration status without revealing its value;
- exact capability and exact host/path templates;
- maximum request count, response bytes and duration;
- conservative rate below the official maximum;
- raw retention decision and checksum behavior;
- target limited to Micron's validated CIK and one explicitly selected filing;
- rollback, storage and development/test database impact.

### Tushare limited Live validation

Before the first request, all of the following must be resolved:

- written/legal determination that the intended project use complies with the
  personal, non-transferable, non-commercial license or a separate suitable license;
- official HTTPS REST endpoint confirmation;
- local `TUSHARE_PRO_TOKEN` reference without secret disclosure;
- exact endpoint entitlement confirmed without broad historical backfill;
- raw, normalized, cache, derived-data, retention and redistribution decisions;
- explicit user approval for one Provider, capability and finite budget.

### A-share disclosure, U.S. EOD and production Embedding

These remain `BLOCKED`. A website being publicly viewable, a technical interface
document existing, or an endpoint being discoverable does not grant automation,
retention, caching or redistribution rights.

## Design conclusion

Only `SEC_EDGAR_PUBLIC_V1` has a sufficiently documented public-access and reuse
foundation to be a conditional production reference adapter. It is still not enabled
and no Live validation has been attempted. Tushare has a well-defined data contract
but a restrictive license and unresolved production transport/storage rights.
A-share disclosure bodies, licensed U.S. EOD and production Embedding remain
explicitly blocked.
