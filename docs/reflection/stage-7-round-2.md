# Stage 7 Reflection — Round 2

Review date: 2026-07-24. Branch:
`stage-7/controlled-agent-orchestration`.

Round 2 rechecked the approved design, all Round 1 fixes, PostgreSQL behavior and
the full offline regression suite. A `PASS` below means the controlled behavior
worked. `BLOCKED BY EVIDENCE` is an honest business-data limitation, not a failed
software assertion.

## Verification matrix

| # | Check | Result | Evidence |
|---:|---|---|---|
| 1 | Current work stays on the Stage 7 branch | PASS | Branch is `stage-7/controlled-agent-orchestration`; no merge was performed. |
| 2 | Production planner is deterministic | PASS | Planner and plan-checksum tests pass for identical request/context/version inputs. |
| 3 | Plan is a finite DAG | PASS | Cycle, self-dependency, unbounded-step and mutation cases are rejected. |
| 4 | Tool Catalog is exact and versioned | PASS | 22 audited source Tools are captured with stable metadata/checksum; eight read-only Research query Tools are separate. |
| 5 | Policy uses exact allowlists | PASS | Prefix/name-pattern authorization is rejected. |
| 6 | Controlled context cannot be overwritten | PASS | Security, Snapshot, as-of, Run, Request, Policy and catalog injection tests pass. |
| 7 | Hard budgets stop execution | PASS | Step, Tool, per-Tool, retry, duration and zero-model-token tests pass. |
| 8 | Pause/resume preserves consumed budgets | PASS | Resume-service tests retain counters and validate all bound versions/context. |
| 9 | Terminal Runs cannot resume | PASS | Domain, repository and database trigger tests pass. |
| 10 | Run transitions append events | PASS | Event sequence and append-only PostgreSQL tests pass. |
| 11 | Production CLI uses the execution service | PASS | Placeholder failure was removed; fixed execution regression passes. |
| 12 | Tool Invocation lifecycle respects immutability | PASS | Invocation is inserted `RUNNING`, then completed once; terminal-update trigger remains enforced. |
| 13 | Tool execution is read-only and offline | PASS | Exact permission, `writes=false`, `requires_network=false` and no-refresh checks pass. |
| 14 | Retry policy is bounded | PASS | Only approved transient failures may retry once; business/security failures do not retry. |
| 15 | No production model provider is enabled | PASS | Model Planner and Reasoner remain `BLOCKED`. |
| 16 | Model token consumption remains zero | PASS | Full Stage 7 tests assert `model_token_budget=0` and consumed tokens 0. |
| 17 | No OpenAI/Anthropic/Gemini/local model call | PASS | Offline/network guards and provider-boundary tests pass. |
| 18 | Scripted providers are test-only | PASS | Production composition rejects scripted test providers. |
| 19 | Evidence belongs to the current Run | PASS | Cross-Run evidence is rejected. |
| 20 | Evidence belongs to the bound Security/Snapshot/as-of | PASS | Cross-context and future-evidence tests pass. |
| 21 | Citation Evidence must be valid | PASS | Invalid Citation evidence cannot enter a valid ledger/package. |
| 22 | Metric Evidence retains calculation lineage | PASS | Calculation Run/Input and formula/source lineage checks pass. |
| 23 | Unknown publication time cannot support strict Claims | PASS | Validator returns non-supported status with explicit reason. |
| 24 | Synthetic evidence is isolated | PASS | Explicit `ResearchMode` plus neutral Synthetic Security tests pass. |
| 25 | Only ClaimSupportValidator finalizes support | PASS | Planner, Tool, Observation and scripted reasoner cannot set `SUPPORTED`. |
| 26 | Numeric Claims retain value/unit/period/as-of/definition | PASS | Schema and validator tests reject incomplete numeric claims. |
| 27 | Conflicts are preserved, not auto-resolved | PASS | Provider/value/currency/unit/context/synthetic conflict tests pass. |
| 28 | Package does not generate investment advice | PASS | Package schema and security tests exclude ratings, target prices, positions and recommendations. |
| 29 | Empty sections are explicit | PASS | `NOT_REQUESTED`, `NO_EVIDENCE`, `BLOCKED` and `PARTIAL` states are deterministic. |
| 30 | Industrial FII real research remains honest | BLOCKED BY EVIDENCE | No approved company body/financial facts; tests require PARTIAL/BLOCKED and prohibit fabricated claims. |
| 31 | Micron real research remains honest | BLOCKED BY EVIDENCE | SEC metadata is not promoted to filing body evidence; prohibited HBM/inventory claims are absent. |
| 32 | Synthetic complete flow is isolated | PASS | Fixture is marked `SYNTHETIC_TEST_ONLY`, `NOT_COMPANY_EVIDENCE`, `OFFLINE`, `NOT_LIVE`. |
| 33 | API exposes only approved GET routes | PASS | Contract tests confirm eight GET routes, safe errors, pagination and `X-Request-ID`; no write methods. |
| 34 | CLI writes are explicit | PASS | Snapshot, research type, Policy and as-of are required; no implicit latest/refresh/network/model behavior. |
| 35 | PostgreSQL model/migration lifecycle is reproducible | PASS | Development and test DB cycles ended at `0006_controlled_research_agent`; prior-stage tables remained. |
| 36 | Full quality gates and offline regression pass | PASS | `uv sync`, Ruff, format, mypy and `1547 passed in 237.82s`; zero failed/errors/skipped/warnings. |

## Round 1 fix recheck

- S7-R1-001: FIXED; production deterministic execution service is composed.
- S7-R1-002: FIXED; resume is validated through the control service.
- S7-R1-003: FIXED; `ResearchMode` replaced the loose synthetic flag.
- S7-R1-004: ACCEPTED LIMITATION; real evidence remains absent and is not fabricated.
- S7-R1-005: FIXED; both database cycles passed.
- S7-R1-006: FIXED; the execution path has a direct regression without invented data.
- S7-R1-007: FIXED; Invocation starts `RUNNING` and completes once.

Unresolved CRITICAL: 0. Unresolved HIGH: 0.

Round 2 conclusion: **CONDITIONAL GO**. Stage 7 engineering contracts are
complete. Real-company research remains PARTIAL/BLOCKED until separately approved,
source-verified company bodies and financial facts exist. No Stage 8 work is
authorized by this conclusion.
