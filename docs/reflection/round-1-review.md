# Round 1 Multi-Role Review

Review date: 2026-07-11. This review evaluates the first complete document set before corrections.

## Role 1 — Financial Data Engineer

| Issue | Severity | Affected files | Evidence | Correction recommendation | Blocks next stage? |
|---|---|---|---|---|---:|
| No authenticated structured A-share financial source | `HIGH` | data matrix, 601138 validation, readiness | Official PDFs work; no Tushare/vendor token exists | Require provider token, personal caching confirmation and reconciliation smoke test before data-adapter implementation | Yes as a condition; backend skeleton can be designed only after user accepts the provider plan |
| Public SSE bars have no documented schema/license/SLA | `HIGH` | data matrix, 601138 validation, ADR-008 | Array returned successfully but endpoint contract not found | Keep as cross-check only; require licensed EOD source | Yes for production data ingestion, not for documentation |
| SEC filing context-selection rules need executable acceptance cases | `MEDIUM` | metric definitions, MU validation | Company Facts has many contexts/custom tags and week-based fiscal periods | Stage 5 must test accession/form/start/end/fy/fp/unit/amendment selection against filings | No for Stage 2 |
| Corporate-action coverage is incomplete for both samples | `HIGH` | sample validations, metrics | MU dividends found but splits not; FII filing actions not normalized | Require one dividend and one split/share-change reconciliation before adjusted-price support | No for Stage 2; blocks Stage 4/5 acceptance |

## Role 2 — Equity Research Analyst

| Issue | Severity | Affected files | Evidence | Correction recommendation | Blocks next stage? |
|---|---|---|---|---|---:|
| Three-scenario valuation method is too abstract to test | `HIGH` | metric definitions, report schema | “selected method” originally lacked eligibility rules | Define minimal testable PE/EV-EBITDA/EV-Revenue/PB templates and company-specific selection; EV/Revenue is not universal | Yes until corrected in Stage 1 docs |
| Industry/competition evidence has no canonical feed | `MEDIUM` | data matrix, CompanyProfile schema | Heterogeneous sources and definitions | Keep narrative module `PARTIAL` when evidence is inadequate; require contrary evidence and source-specific definitions | No |
| Data volume could be mistaken for analysis | `MEDIUM` | report schema, Reflection | Many facts/metrics do not by themselves form a thesis | Require core conclusion, causal inference, contrary evidence, monitoring and proof/disproof conditions | No; already largely covered |
| Scenario multiples could look like consensus | `HIGH` | product scope, metrics, report schema | Consensus and Forward PE are excluded | Label every multiple as user/model assumption with source/rationale; prohibit “consensus” label | No after correction |

## Role 3 — AI and Agent Architect

| Issue | Severity | Affected files | Evidence | Correction recommendation | Blocks next stage? |
|---|---|---|---|---|---:|
| Fixed-flow versus Agent autonomy is sufficiently clear | `LOW` | ADR-001, tool design | Agent cannot alter identity/cutoff/calculations and only has filtered read tools | Preserve and enforce via policy tests | No |
| Reflection could become paraphrase churn without change detection | `MEDIUM` | ADR-005, reflection design | Two-round limit exists, but implementation must compare targeted hashes | Require before/after pointer hashes and `NO_NEW_EVIDENCE` stop test | No; design corrected in schema |
| MCP plan could invite premature implementation | `LOW` | ADR-006, MCP roadmap | Servers are named although V0.1 excludes them | Keep entry gates explicit and do not create server code before Stage 9 | No |
| RAG evidence and structured calculations are correctly separated | `LOW` | ADR-004, RAG design | Vector search cannot supply canonical numbers | Preserve with integration tests | No |

## Role 4 — Security Engineer

| Issue | Severity | Affected files | Evidence | Correction recommendation | Blocks next stage? |
|---|---|---|---|---|---:|
| External-document prompt injection is a primary threat | `HIGH` | security, RAG, tool design | Filings/HTML can contain arbitrary text and links | Maintain untrusted-data channels, sanitizer, tool-policy intersection and adversarial corpus | No for Stage 2 skeleton; blocks Stage 6 acceptance |
| Public/remote URL acquisition can become SSRF | `HIGH` | security, RAG, MCP roadmap | Future filing links and redirects are external | Validate canonical domain/path and every redirect; reject private IP/schemes/ports | No after documented controls |
| SEC archive 403 demonstrates operational security/rate sensitivity | `MEDIUM` | environment, MU validation, data matrix | Isolated 200 followed by repeat-probe 403 | Use real contact User-Agent, cache/bulk, low internal limit, backoff and circuit breaker | No |
| Dirty unrelated repository risks accidental data/secret staging | `HIGH` | environment, readiness | Many unrelated untracked files and modified portfolio source | Require dedicated repository and scoped Git commands | Yes for Stage 2 |

## Role 5 — Product and Compliance Reviewer

| Issue | Severity | Affected files | Evidence | Correction recommendation | Blocks next stage? |
|---|---|---|---|---|---:|
| Current workspace is the portfolio repository | `HIGH` | environment, readiness | Existing Vite website and portfolio-specific AGENTS.md | User must select a dedicated Stock Research Agent directory/repository before Stage 2 | Yes |
| Tencent Cloud mainland + OpenAI is not an approved deployment assumption | `CRITICAL` | deployment, readiness, risk register | OpenAI supported-country list omits mainland China; desktop 401 is only transport proof | Choose a supported deployment/model-provider strategy and obtain terms/compliance review; do not design circumvention | Yes if deployment/model choice affects Stage 2 configuration; explicitly conditional |
| Market-data display/redistribution rights are unresolved | `HIGH` | data matrix, compliance | SSE website, CNINFO, Nasdaq website and provider terms do not establish future public display | Keep V0.1 local/personal; require new license review before frontend/public service | No for local Stage 2; blocks Stage 10/public use |
| Docker and ordinary terminal runtimes are unavailable | `HIGH` | environment, readiness | Commands absent from PATH; only Codex runtime works | Before Stage 2, install/verify Docker or approve a documented local non-Docker path; configure Python/Git | Yes as an environment choice |
| V0.1 is broad but bounded by two securities and staged implementation | `MEDIUM` | product scope | Two markets, RAG, valuation and Reflection remain substantial | Preserve two-security gate; implement one vertical slice at a time and allow `PARTIAL` modules | No |

## Round 1 disposition

- `CRITICAL`: 1, explicitly unresolved and conditional on deployment/model strategy.
- `HIGH`: 11, including four Stage 2 entry conditions and several later-stage acceptance blockers.
- `MEDIUM`: 6.
- `LOW`: 3.

Corrections applied after this review and final closeout: testable valuation templates with company-specific selection, stronger PARTIAL behavior, precise blocker classes, SEC endpoint separation and environment/runtime provenance. No finding was hidden by downgrading an unverified source.
