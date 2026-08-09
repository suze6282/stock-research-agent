# Stage 7 Reflection — Round 1

Review date: 2026-07-24. Scope: branch
`stage-7/controlled-agent-orchestration`, Tasks 1–41. Severity vocabulary:
CRITICAL, HIGH, MEDIUM, LOW.

## Findings

| ID | Role | Severity | Description | Evidence | Impacted files | Fix | Blocking | Status |
|---|---|---|---|---|---|---|---|---|
| S7-R1-001 | Agent architecture | HIGH | The explicit `agent run` command persisted a valid Plan but terminated with `EXECUTION_ADAPTER_NOT_COMPOSED`. | Original `cli_agent._plan_or_run`; RED execution-pipeline regression. | `src/stock_research_agent/cli_agent.py`, `domain/research_agent/application.py`, execution tests | Added the finite deterministic execution service, exact multi-registry routing, audited persistence, budget update and package terminalization. | Yes | FIXED |
| S7-R1-002 | Tool security | HIGH | CLI `resume` used a direct state transition without revalidating Policy, Tool Catalog, Snapshot ownership/as-of or remaining steps. | Original `cli_agent._control`; resume-service tests. | `src/stock_research_agent/cli_agent.py` | Routed resume through `ResearchRunControlService`; exact Policy/catalog/Snapshot/security/as-of values are revalidated and consumed budgets are retained. | Yes | FIXED |
| S7-R1-003 | Evidence and Citation | MEDIUM | Synthetic Claim construction used a raw `allow_synthetic` boolean. | Original `DeterministicClaimBuilder.propose_claims`; synthetic-flow regression. | `src/stock_research_agent/domain/research_agent/claims.py` | Replaced the loose flag with explicit `ResearchMode`; only `SYNTHETIC_TEST_ONLY` enables synthetic proposals and final validation still fails closed. | No | FIXED |
| S7-R1-004 | Financial research | LOW | Real-company acceptance is based on verified absence and contract fixtures, not a completed company research result. | Industrial FII and Micron acceptance tests. | Stage report and README | Preserved `CONDITIONAL GO`; both real-company document/financial research results remain honestly PARTIAL/BLOCKED. | No | ACCEPTED LIMITATION |
| S7-R1-005 | Database | LOW | Twelve-table migration, restrictive FKs, triggers, downgrade, transaction rollback and model parity had passed, but final cycles remained. | Final PostgreSQL and Alembic commands. | migration/repository/PostgreSQL tests | Full suite passed; development and isolated test databases both completed downgrade/upgrade and ended at `0006_controlled_research_agent`. | No | FIXED |
| S7-R1-006 | Testing and reliability | MEDIUM | Golden values were independent, but the CLI run path had not exercised the production execution adapter. | Execution-pipeline regression plus CLI contract tests. | execution and CLI tests | Added a direct production-service regression covering fixed Tool execution, persistence, budgets and honest failed package behavior. A fabricated COMPLETE real-company Snapshot was deliberately not added. | No | FIXED |
| S7-R1-007 | Database / immutability | HIGH | The new execution adapter initially inserted a Tool Invocation in its terminal status and then called completion, which conflicts with terminal immutability triggers. | RED assertion in `test_research_agent_execution_pipeline.py`; repository trigger contract. | `domain/research_agent/application.py`, execution-pipeline test | Invocation is inserted as `RUNNING`, then completed once with the executor's terminal status and checksum/error metadata. | Yes | FIXED |

## Role conclusions

- Agent architecture: finite Planner, hard budgets, version binding, production
  deterministic execution and immutable audit records pass.
- Financial research: missing evidence is not converted to financial or business
  Claims.
- Tool security: exact allowlist and controlled context reject scope expansion.
- Database: schema/model parity and rollback behavior pass PostgreSQL checks.
- Evidence and Citation: only the deterministic validator assigns final support;
  conflict evidence is preserved.
- Testing and reliability: 150 focused Stage 7 tests and the full 1547-test suite
  pass; no skipped tests or warnings were reported.

Unresolved CRITICAL: 0. Unresolved HIGH: 0.
