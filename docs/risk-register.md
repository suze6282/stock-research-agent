# Risk Register

## Stage 4 active risks

- Live `TUSHARE_PRO` is `BLOCKED` pending a real token and use/cache permission.
- Licensed U.S. EOD is `BLOCKED` pending Provider selection, entitlement and key.
- `SEC_ARCHIVES` is `BLOCKED` pending a real contact/User-Agent and authorized adapter.
- Fixture crops are reproducible `FIXTURE/OFFLINE/NOT_LIVE` evidence, not current data.
- Unknown `source_published_at` forces `PARTIAL`; it is not inferred from retrieval.
- Full exchange calendars, 财务标准化 and metric calculation are outside Stage 4.

Blocking class is one of `BLOCKS_STAGE_2`, `BLOCKS_DATA_INTEGRATION`, `BLOCKS_PRODUCTION`, or `NON_BLOCKING`.

| Risk ID | Risk description | Probability | Impact | Current evidence | Mitigation | Owner | Deadline stage | Status | Blocking class |
|---|---|---|---|---|---|---|---:|---|---|
| R-001 | Stock project is mixed into an unrelated dirty portfolio repo | `HIGH` | `HIGH` | Existing Vite site, portfolio AGENTS.md and unrelated worktree changes | Choose dedicated repo or explicitly approve monorepo boundary; scoped staging | User + stage lead | 2 | `OPEN` | `BLOCKS_STAGE_2` |
| R-002 | User shell cannot reproduce Python/Git commands | `HIGH` | `HIGH` | Python resolves to Store alias and exits 9009; Git not found | Install/pin user-accessible Python and Git; verify bootstrap outside Codex | User + engineering | 2 | `OPEN` | `BLOCKS_STAGE_2` |
| R-003 | Docker is absent | `HIGH` | `MEDIUM` | Command and common paths absent | Install/verify Docker **or** approve/test non-Docker PostgreSQL/service path | User + engineering | 2 | `OPEN` | `BLOCKS_STAGE_2` only if no alternative is approved |
| R-004 | No authenticated/licensed structured A-share financial source | `HIGH` | `HIGH` | No key; only official PDFs/Tushare docs validated | Select provider/token, confirm cache rights, reconcile sample facts | User + data engineer | 4 | `OPEN` | `BLOCKS_DATA_INTEGRATION` |
| R-005 | No licensed U.S. EOD/corporate-action source | `HIGH` | `HIGH` | Nasdaq website is only a cross-check | Select licensed plan and validate MU history/actions | User + data engineer | 4 | `OPEN` | `BLOCKS_DATA_INTEGRATION` |
| R-006 | SEC Archive access is client/time-sensitive and primary documents are classified as undeclared automation | `HIGH` under current UA | `HIGH` | Submissions/Company Facts 200; Python index/documents 403; same-header .NET index retry 200/valid JSON, documents still 403 | User supplies real contact; pin one HTTP client; compliant UA; low rate, backoff, bulk/cache; repeated acceptance run | User + data engineer | 4 | `OPEN` | `BLOCKS_DATA_INTEGRATION` |
| R-007 | Missing corporate actions corrupt shares or adjusted prices | `MEDIUM` | `HIGH` | Dividend found; split/full adjustment not verified | Licensed action feed and event reconciliation | Data engineer | 5 | `OPEN` | `BLOCKS_DATA_INTEGRATION` |
| R-008 | A-share cumulative quarters are double-counted | `HIGH` without controls | `HIGH` | FII Q3 statements are cumulative | Deterministic differencing and fixtures | Financial data engineer | 5 | `MITIGATED_BY_DESIGN` | `NON_BLOCKING` for Stage 2 |
| R-009 | U.S. XBRL context/custom-tag selection is wrong | `HIGH` without controls | `HIGH` | Company Facts has multiple contexts; Archive currently blocked | Context rules, compliant Archive access and filing reconciliation | Financial data engineer | 5 | `OPEN` | `BLOCKS_DATA_INTEGRATION` for filing-level normalization |
| R-010 | Future data leaks into historical research | `MEDIUM` | `CRITICAL` | Replays can retrieve later corrections | Frozen cutoff, immutable snapshots and leakage tests | Architecture + QA | 5 | `MITIGATED_BY_DESIGN` | `NON_BLOCKING` for Stage 2 |
| R-011 | Filing/HTML prompt injection causes tool misuse | `HIGH` over project life | `CRITICAL` | All documents are untrusted | Sanitization, fixed policy, egress/tool allowlists, adversarial tests | Security | 6 | `MITIGATED_BY_DESIGN` | `BLOCKS_PRODUCTION` if controls untested |
| R-012 | Market-data cache/display/redistribution exceeds licence | `MEDIUM` personal / `HIGH` public | `CRITICAL` | Multiple permissions remain unverified | Personal-only boundary; contract register; new review before public use | Compliance + user | 4/10 | `OPEN` | `BLOCKS_PRODUCTION`; may also block affected data integration |
| R-013 | Mainland deployment assumes unsupported OpenAI API use | `HIGH` if mainland chosen | `CRITICAL` | Official list omits mainland China; only public endpoint reachability tested | Choose authorized region/model provider; no circumvention | User + compliance/architecture | 10 | `OPEN` | `BLOCKS_PRODUCTION` |
| R-014 | Secrets enter model/log/Git | `MEDIUM` | `CRITICAL` | Future adapters require credentials; current repo dirty | Secret manager, adapter-only access, redaction/secret scanning | Security + engineering | 4/10 | `MITIGATED_BY_DESIGN` | `BLOCKS_PRODUCTION` if controls untested |
| R-015 | Scenario values create false precision | `MEDIUM` | `HIGH` | Valuation methods require assumptions | Company-specific method selection, sensitivity, SCENARIO class | Research + product | 7 | `MITIGATED_BY_DESIGN` | `NON_BLOCKING` for Stage 2 |
| R-016 | RAG citation does not support claim | `HIGH` without validation | `HIGH` | Retrieval relevance is not entailment | Exact citation, evidence checks and PARTIAL fallback | AI/RAG + QA | 6/8 | `MITIGATED_BY_DESIGN` | `BLOCKS_PRODUCTION` if unvalidated |
| R-017 | Tencent/provider/model connectivity fails in target region | `MEDIUM` | `HIGH` | No target deployment exists | Provision region, authenticated smoke tests, egress monitoring/fallback | Operations | 10 | `OPEN` | `BLOCKS_PRODUCTION` |
| R-018 | V0.1 scope overruns | `HIGH` | `MEDIUM` | Two markets and full research workflow | Fixed stages, two samples, PARTIAL modules | Product/stage lead | Every stage | `MONITORING` | `NON_BLOCKING` |
| R-019 | Approved offline samples contain no numeric financial facts | `HIGH` | `HIGH` | Industrial FII has one price item; Micron has price and filing metadata only | Keep normalization/metrics `BLOCKED/NULL`; acquire licensed/authorized numeric evidence before production validation | User + financial data engineer | 5/6 | `OPEN` | `BLOCKS_DATA_INTEGRATION` |
| R-020 | Provider concept mappings are incorrectly auto-approved | `MEDIUM` | `CRITICAL` | Custom taxonomies and labels vary by provider | Exact versioned rules only; evidence/reviewer required; unmapped/ambiguous raw facts retained | Accounting/data owner | Every mapping release | `MITIGATED_BY_DESIGN` | `BLOCKS_PRODUCTION` if controls bypassed |
| R-021 | Metric outputs are mistaken for recommendations | `MEDIUM` | `HIGH` | Deterministic ratios can appear authoritative despite incomplete evidence | Typed quality/N/M warnings, full lineage, no narrative/target price, analyst limitations in docs | Product + research | 6/7 | `MITIGATED_BY_DESIGN` | `NON_BLOCKING` |
# Stage 6 open risks

- Industrial FII and Micron have no compliant stored company body: acceptance is BLOCKED.
- Production embeddings are not configured: VECTOR is BLOCKED and HYBRID lexical fallback is PARTIAL.
- pypdf reading order and standard-library HTML structure are best effort: complex documents may be PARTIAL.
- Cache-only Tool/API requires an explicit CLI/internal Retrieval Run before reads can return evidence.
# Stage 7 residual risks

- Industrial FII verified company body: BLOCKED.
- Micron verified company body: BLOCKED.
- Production model planning/reasoning: BLOCKED by design.
- Live Tushare, licensed U.S. EOD, and SEC Archive access remain BLOCKED.
- Synthetic test Evidence could be misrepresented if markers are ignored;
  production admission and Claim validation therefore reject it for real runs.
- Historical runs must remain bound to exact Snapshot, Policy, planner, and
  `tool_catalog_version`.

Current release judgment: `CONDITIONAL GO`.

# Stage 8 residual risks

| ID | Risk | State | Control / exit condition |
|---|---|---|---|
| R8-01 | Report mistaken for advice or public publication | CONTROLLED | Internal-only Gate; no rating, target, position, trade or publish action |
| R8-02 | Missing real-company body/financial evidence hidden | BLOCKED | Industrial FII and Micron stay PARTIAL/BLOCKED until verified records exist |
| R8-03 | Synthetic evidence contaminates company research | CONTROLLED | Four markers, neutral IDs and real-company rejection tests |
| R8-04 | Model output bypasses deterministic validation | BLOCKED | Production Narrative/Reflection disabled; token budget zero |
| R8-05 | Citation excerpt exposes content or secrets | CONTROLLED | VALID locator/checksum, 1000-character bound, no raw document/path |
| R8-06 | Immutable history altered | CONTROLLED | RESTRICT FKs, checks, indexes and PostgreSQL triggers |
| R8-07 | Live providers/production Embedding unavailable | BLOCKED | Offline deterministic path; later stage needs explicit authorization |
