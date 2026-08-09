# Report Schema V0.1

This is a design contract, not generated code. Schemas are modular and versioned independently.

## Common conventions

Every module contains:

| Field | Type | Required | Meaning |
|---|---|---:|---|
| `schema_version` | string | yes | Semantic version of this module. |
| `generated_at` | datetime with timezone | yes | Module generation time. |
| `research_as_of_time` | datetime with timezone | yes | Fixed research cutoff. |
| `data_snapshot_id` | UUID/string | yes | Immutable snapshot reference. |
| `source_refs` | array of `SourceRef` | yes | May be empty only for a container module. |
| `warnings` | array of `Warning` | yes | Empty array when none. |
| `status` | enum `COMPLETE/PARTIAL/FAILED` | yes | Module status. |

`null` is the only JSON missing value. A null analytical field must have a corresponding `missing_reason` (`SOURCE_MISSING`, `NOT_APPLICABLE`, `NOT_MEANINGFUL`, `INCOMPATIBLE_PERIOD`, `INCOMPATIBLE_UNIT`, `INCOMPATIBLE_CURRENCY`, `AS_OF_UNAVAILABLE`, `POLICY_BLOCKED` or `VALIDATION_FAILED`). Empty string, zero and `"N/A"` are not missing values.

`SourceRef` includes `source_ref_id`, provider, source type, authority class, source identifier/accession, URL, title, security/issuer ID, report period, `source_published_at`, `retrieved_at`, content hash, parser version and optional page/anchor. `Warning` includes code, severity, message and affected JSON pointers.

Every research claim uses:

```text
claim_id
claim_type: FACT | CALCULATION | INFERENCE | SCENARIO | UNVERIFIED
text or structured_value
confidence: HIGH | MEDIUM | LOW
source_ref_ids
calculation_ref_id (when applicable)
as_of_time
warnings
```

`UNVERIFIED` claims may appear only in gaps/appendices and cannot enter the executive/core conclusion. Confidence is categorical; pseudo-precise numbers such as `0.72` are prohibited.

## SecurityIdentityOutput

| Field | Type | Required | Source/time notes |
|---|---|---:|---|
| `issuer_id`, `legal_name` | string | yes | Master/official source; identity effective time. |
| `security_id`, `symbol`, `exchange`, `market` | string | yes | Security-level source. |
| `currency` | ISO 4217 string | yes | Trading currency. |
| `security_type`, `listing_status` | enum/string | yes | Null+reason if status not verified. |
| `cik` | string/null | conditional | Required for U.S. SEC registrant. |
| `aliases` | array | yes | Alias value, type, language, effective dates and source. |
| `issuer_security_relationship` | object | yes | Prevents company/security conflation. |

Module-specific warnings cover ambiguous symbol, stale status, multiple securities and unsupported security type.

## DataSnapshotOutput

| Field | Type | Required | Source/time notes |
|---|---|---:|---|
| `data_snapshot_id` | string | yes | Immutable primary key. |
| `research_as_of_time` | datetime | yes | Fixed before acquisition. |
| `source_items` | array | yes | Provider, source ID, published/filed/amended/retrieved times, checksum, eligibility result. |
| `price_observation` | object/null | yes | Market date/timezone, close, currency, raw/adjusted basis, provider. |
| `financial_periods` | array | yes | Fiscal labels, start/end, annual/discrete/YTD, units/currency, filing version. |
| `corporate_action_state` | object/null | yes | Shares/adjustment basis and gaps. |
| `formula_version`, `prompt_version`, `model_version` | string | yes | Reproducibility fields. |
| `parser_versions`, `adapter_versions` | object | yes | Per source/tool. |

Warnings cover cutoff exclusion, stale price, missing period, provider conflict and incomplete corporate actions.

## CompanyProfileOutput

| Field | Type | Required | Source/time notes |
|---|---|---:|---|
| `business_model_claims` | array of Claim | yes | Filing/issuer evidence. |
| `segments` | array | yes | Name, description, reported metrics, period and sources; may be empty with reason. |
| `geographies`, `customers_suppliers` | arrays | no | Only disclosed, non-invented information. |
| `industry_context_claims`, `competitive_position_claims` | arrays | yes | Inference must cite supporting facts and contrary evidence. |
| `data_gaps` | array | yes | Explicit unresolved profile questions. |

## FinancialAnalysisOutput

| Field | Type | Required | Source/time notes |
|---|---|---:|---|
| `annual_periods` | array | yes | Target three; each has period, facts, currency/unit, source and gaps. |
| `quarterly_periods` | array | yes | Target four discrete; records derivation from YTD/FY. |
| `metrics` | array of `MetricResult` | yes | Key, Decimal-as-string, period, formula/version, inputs, lineage, missing reason. |
| `cash_flow_quality`, `balance_sheet_quality`, `earnings_quality` | arrays of Claim | yes | Calculations separated from inference. |
| `conflicts` | array | yes | Provider/filing conflicts and resolution. |

`MetricResult.value` is a decimal string, `null`, or semantic `NM`; JSON numbers are avoided for financial precision.

## ValuationOutput

| Field | Type | Required | Source/time notes |
|---|---|---:|---|
| `valuation_date`, `price_ref`, `share_count_ref` | string/object | yes | Aligns market and share basis. |
| `observed_valuation_metrics` | array | yes | PE/PB/PS/EV/EV-EBITDA/FCF yield with formula lineage. |
| `scenarios` | exactly three objects | yes | `BEAR`, `BASE`, `BULL`. |
| `method_selection` | object | yes | Candidate methods, selected method, deterministic eligibility checks, cyclicality/profitability rationale, rejected methods and fallback reason. |
| `scenario_method`, `horizon` | enum/string + date | yes | Method may be `PE_NORMALIZED`, `EV_EBITDA_NORMALIZED`, `EV_REVENUE`, or `PB`; horizon is explicit and versioned, not permanently fixed. |
| `assumptions` | array | yes | Name, Decimal value, unit, source/author, rationale, sensitivity bounds. |
| `calculation_steps` | array | yes | Deterministic and replayable. |
| `equity_value`, `per_share_value` | Decimal string/null | yes | `SCENARIO`, never fact. |
| `sensitivity`, `invalidation_conditions` | arrays | yes | Shows uncertainty and falsifiers. |

The V0.1 calculation follows the eligible template in `metric-definitions-v0.1.md`. Missing required inputs make that method `UNAVAILABLE`; the module may become `PARTIAL` or use a documented fallback. It never switches methods silently. All growth, normalized earnings/EBITDA/revenue/book values and exit multiples remain `SCENARIO` assumptions.

## CatalystRiskOutput

| Field | Type | Required | Source/time notes |
|---|---|---:|---|
| `catalysts`, `risks` | arrays | yes | Each has claim, horizon, mechanism, evidence, contrary evidence and monitoring metric. |
| `supporting_evidence`, `contrary_evidence` | arrays | yes | Citation IDs, not free text only. |
| `proof_conditions`, `disproof_conditions` | arrays | yes | Observable indicators, direction, period and threshold/rationale where justified. |
| `unknowns` | array | yes | Unverified items excluded from core conclusion. |

## ReflectionResult

| Field | Type | Required | Source/time notes |
|---|---|---:|---|
| `reflection_version` | string | yes | Validator strategy version. |
| `rounds_run` | integer 0–2 | yes | Hard maximum 2. |
| `checks` | array | yes | Rule ID, layer, status, evidence and affected pointer. |
| `findings` | array | yes | Severity, issue, correction and resolution. |
| `changes` | array | yes | Targeted JSON pointer plus before/after hashes. |
| `stop_reason` | enum | yes | `PASSED`, `MAX_ROUNDS`, `NO_NEW_EVIDENCE`, `UNSAFE`, `UNRECOVERABLE`. |
| `final_status` | `FINAL/PARTIAL/FAILED` | yes | Governs report publication. |

## FinalResearchReport

| Field | Type | Required | Source/time notes |
|---|---|---:|---|
| `report_id`, `report_schema_version` | string | yes | Stable report identity/version. |
| `identity_ref`, `snapshot_ref` | module reference | yes | No copied divergent identity/snapshot. |
| `company_profile`, `financial_analysis`, `valuation`, `catalyst_risk` | module reference | yes | A module may be `PARTIAL`, not omitted. |
| `core_conclusion` | array of validated Claim | yes | No `UNVERIFIED`; scenarios labeled. |
| `data_cutoff_summary`, `data_gaps` | object/array | yes | Human-visible. |
| `reflection_result` | module reference | yes | Must allow final status. |
| `disclaimer` | string/version | yes | Not a substitute for compliance controls. |
| `markdown_render` | string/object | yes | Derived view with the same report hash. |

The final report fails schema validation if it lacks cutoff, price time, currency/unit, formula paths, citations, contrary evidence, gaps, invalidation conditions or disclaimer.
